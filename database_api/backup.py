import os
import errno
import shutil
import threading
import subprocess
from urllib.parse import urlparse
from datetime import datetime, timedelta

from api.telegram import send_telegram_message
from api.settings import BACKUP_DAYS, BACKUP_FOLDER, POSTGRES_DOCKER_CONTAINER
from api.storage import upload_file, get_all_filenames, delete_file


PG_DUMP_FLAGS = ['--blobs', '--clean', '-Fc', '--verbose']
PG_RESTORE_FLAGS = ['--verbose', '--no-privileges', '--no-owner']
BACKUP_EXTENSION = '.dump'
BACKUP_DATE_FORMAT = '%y%m%d%H%M%S'
DISK_FULL_MARKERS = ('no space left on device', 'disk quota exceeded', 'quota exceeded')
# Path fisso, non configurabile: il dump di fallback deve stare sul disco del
# server e sopravvivere alla ricreazione del container, quindi va montato uguale
# in tutti i progetti che usano db_backup.
BACKUP_FALLBACK_FOLDER = '/opt/db-backup-fallback'


def data_export(db_url: str):
  filename = f'{datetime.now().strftime(BACKUP_DATE_FORMAT)}{BACKUP_EXTENSION}'

  if POSTGRES_DOCKER_CONTAINER:
    _docker_pg_dump(db_url, filename)
  else:
    _local_pg_dump(db_url, filename)

  return filename


def data_import(db_url: str, filename: str):
  if not os.path.exists(filename):
    raise FileNotFoundError(f'File non trovato: {filename}')

  parsed = urlparse(db_url)
  db_name = parsed.path.lstrip('/')
  admin_url = parsed._replace(path='/postgres').geturl()
  if (
    input(
      f'Vuoi sovrascrivere il database "{db_name}"? '
      'Questa operazione comporterà la cancellazione di tutti i dati. [y/N]: '
    )
    .strip()
    .lower()
  ) != 'y':
    raise RuntimeError('Operazione annullata dall’utente')

  try:
    _recreate_database(admin_url, db_name)

    if POSTGRES_DOCKER_CONTAINER:
      _docker_pg_restore(db_url, filename)
    else:
      _local_pg_restore(db_url, filename)

  except subprocess.CalledProcessError as e:
    details = (e.stderr or e.stdout or '').strip()
    raise RuntimeError(
      f'Import del database "{db_name}" non riuscito.\n'
      f'{details or f"Il comando è terminato con codice di uscita {e.returncode}."}\n'
      'Assicurati che il servizio Postgres sia raggiungibile e che non ci siano '
      'connessioni attive al database prima di ripetere l’operazione.'
    ) from e


def db_backup(db_url: str, server=None):
  def run():
    filename = None
    try:
      if not BACKUP_FOLDER:
        raise ValueError('BACKUP_FOLDER non configurata')

      filename = data_export(db_url)
      upload_backup(filename, server)
      delete_file(filename, '', ignore_dev=True)

      cleanup_old_backups(server)
      flush_fallback_backups(server)

    except Exception as e:
      report_failed_backup(db_url, e, filename, server)

  thread = threading.Thread(target=run, daemon=True)
  thread.start()


def upload_backup(file_path: str, server=None):
  with open(file_path, 'rb') as content:
    upload_file(content, os.path.basename(file_path), BACKUP_FOLDER, server, 'postgres-backup', True)


def report_failed_backup(db_url: str, error: Exception, file_path: str = None, server=None):
  title = '**📦 DB Backup Fallito**'
  if is_disk_full(error):
    title = '**📦 DB Backup Fallito — spazio esaurito**'

  message = [
    f'{title}\n▶️ `{db_url}`\n',
    f'**❌ Errore durante il backup ({"server" if server else "local"}):**',
    f'`{error_details(error)}`',
  ]

  if file_path and os.path.exists(file_path):
    message.append(keep_dump_locally(file_path))

  send_telegram_message('\n'.join(message))


def keep_dump_locally(file_path: str) -> str:
  try:
    os.makedirs(BACKUP_FALLBACK_FOLDER, exist_ok=True)
    fallback_path = shutil.move(file_path, os.path.join(BACKUP_FALLBACK_FOLDER, os.path.basename(file_path)))
    return f"\n**💾 Dump salvato in locale:** `{fallback_path}`\nVerra' ricaricato al primo backup riuscito."

  except OSError as e:
    return f'\n**🛑 Dump perso:** salvataggio di fallback non riuscito in `{BACKUP_FALLBACK_FOLDER}`\n`{e}`'


def flush_fallback_backups(server=None):
  if not os.path.isdir(BACKUP_FALLBACK_FOLDER):
    return

  recovered = []
  for filename in sorted(os.listdir(BACKUP_FALLBACK_FOLDER)):
    fallback_path = os.path.join(BACKUP_FALLBACK_FOLDER, filename)
    if not os.path.isfile(fallback_path) or parse_backup_date(filename) is None:
      continue

    try:
      upload_backup(fallback_path, server)
      os.remove(fallback_path)
      recovered.append(filename)

    except Exception as e:
      send_telegram_message(
        '\n'.join(
          [
            f'**📦 Recupero Dump di Fallback Fallito**\n▶️ `{fallback_path}`\n',
            f'**❌ Errore durante il ricaricamento ({"server" if server else "local"}):**',
            f'`{error_details(e)}`',
            '\nIl dump resta in locale, si riprova al prossimo backup.',
          ]
        )
      )
      break

  if recovered:
    send_telegram_message(
      '\n'.join([f'**📦 Dump di Fallback Ricaricati ({len(recovered)})**\n'] + [f'▶️ `{name}`' for name in recovered])
    )


def is_disk_full(error: Exception) -> bool:
  if isinstance(error, OSError) and error.errno in (errno.ENOSPC, errno.EDQUOT):
    return True

  details = error_details(error).lower()
  return any(marker in details for marker in DISK_FULL_MARKERS)


def error_details(error: Exception) -> str:
  if not isinstance(error, subprocess.CalledProcessError):
    return str(error)

  output = (error.stderr or error.stdout or '').strip()
  return output or f"Il comando e' terminato con codice di uscita {error.returncode}"


def cleanup_old_backups(server=None):
  """Elimina i dump piu' vecchi di BACKUP_DAYS giorni.

  L'eta' del dump si ricava dal nome del file, non dal filesystem: in modalita'
  server i path restituiti dal listing vivono sulla macchina di backup e non
  sono raggiungibili da qui. I dump nascono da data_export come
  `%y%m%d%H%M%S.dump`, quindi il nome e' l'unica fonte disponibile in entrambe
  le modalita'. Un nome che non rispetta il formato viene tenuto: meglio un
  file di troppo che una cancellazione basata su un'ipotesi.
  """
  expiration = datetime.now() - timedelta(days=BACKUP_DAYS)

  for file_path in get_all_filenames(BACKUP_FOLDER, server, 'postgres-backup', True):
    backup_date = parse_backup_date(file_path)
    if backup_date is None or backup_date > expiration:
      continue

    delete_file(os.path.basename(file_path), BACKUP_FOLDER, server, os.path.dirname(file_path) or None, True)


def parse_backup_date(file_path: str) -> datetime | None:
  filename = os.path.basename(file_path)
  if not filename.lower().endswith(BACKUP_EXTENSION):
    return None

  try:
    return datetime.strptime(filename[: -len(BACKUP_EXTENSION)], BACKUP_DATE_FORMAT)
  except ValueError:
    return None


def _recreate_database(admin_url: str, db_name: str):
  _run_admin_sql(admin_url, f'DROP DATABASE IF EXISTS "{db_name}";')
  _run_admin_sql(admin_url, f'CREATE DATABASE "{db_name}";')


def _run_admin_sql(admin_url: str, sql: str):
  command = ['psql', admin_url, '-v', 'ON_ERROR_STOP=1', '-c', sql]

  if POSTGRES_DOCKER_CONTAINER:
    command = ['docker', 'exec', POSTGRES_DOCKER_CONTAINER, *command]

  subprocess.run(command, check=True, capture_output=True, text=True)


def _docker_pg_dump(db_url: str, filename: str):
  container_path = f'/tmp/{filename}'
  _run_in_container(['pg_dump', f'--dbname={db_url}', *PG_DUMP_FLAGS, '-f', container_path])
  try:
    _copy_from_container(container_path, filename)
  finally:
    _run_in_container(['rm', container_path])


def _docker_pg_restore(db_url: str, filename: str):
  container_path = f'/tmp/{os.path.basename(filename)}'
  _copy_to_container(filename, container_path)
  try:
    _run_in_container(['pg_restore', f'--dbname={db_url}', *PG_RESTORE_FLAGS, container_path])
  finally:
    _run_in_container(['rm', container_path])


def _local_pg_dump(db_url: str, filename: str):
  subprocess.run(['pg_dump', f'--dbname={db_url}', *PG_DUMP_FLAGS, '-f', filename], check=True)


def _local_pg_restore(db_url: str, filename: str):
  subprocess.run(['pg_restore', f'--dbname={db_url}', *PG_RESTORE_FLAGS, filename], check=True)


def _run_in_container(command: list):
  subprocess.run(['docker', 'exec', POSTGRES_DOCKER_CONTAINER, *command], check=True)


def _copy_to_container(host_path: str, container_path: str):
  subprocess.run(['docker', 'cp', host_path, f'{POSTGRES_DOCKER_CONTAINER}:{container_path}'], check=True)


def _copy_from_container(container_path: str, host_path: str):
  subprocess.run(['docker', 'cp', f'{POSTGRES_DOCKER_CONTAINER}:{container_path}', host_path], check=True)
