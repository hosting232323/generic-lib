import os
import errno
import shutil
import threading
import subprocess
from urllib.parse import unquote, urlparse, urlsplit
from datetime import datetime

from api.telegram import send_telegram_message
from api.settings import BACKUP_FOLDER, POSTGRES_DOCKER_CONTAINER, PROJECT_NAME
from api.storage import upload_db_dump, cleanup_db_dumps, download_db_dump, delete_file


PG_DUMP_FLAGS = ['--blobs', '--clean', '-Fc', '--verbose']
PG_RESTORE_FLAGS = ['--verbose', '--no-privileges', '--no-owner']
BACKUP_EXTENSION = '.dump'
BACKUP_DATE_FORMAT = '%y%m%d%H%M%S'
DISK_FULL_MARKERS = ('no space left on device', 'disk quota exceeded', 'quota exceeded')
BACKUP_FALLBACK_ROOT = '/opt/db-backup-fallback'
BACKUP_DISK_THRESHOLD = 90
BACKUP_FALLBACK_FOLDER = os.path.join(BACKUP_FALLBACK_ROOT, PROJECT_NAME)
# I dump vivono in un repository restic, cifrato con RESTIC_PASSWORD come quello
# di folder_backup: sulla macchina di backup non resta mai un dump in chiaro.
DB_BACKUP_REPOSITORY = 'db-backup'
DB_BACKUP_FILENAME = 'database.dump'


class LocalDiskAlmostFullError(Exception):
  """Il disco del sistema operativo ha superato la soglia: il dump non parte."""


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

      check_local_disk_usage()

      filename = data_export(db_url)
      upload_backup(filename, server)
      delete_file(filename, '', ignore_dev=True)

      cleanup_old_backups(server)

    except Exception as e:
      report_failed_backup(db_url, e, filename, server)

  thread = threading.Thread(target=run, daemon=True)
  thread.start()


def upload_backup(file_path: str, server=None):
  upload_db_dump(file_path, db_backup_repository(), DB_BACKUP_FILENAME, server)


def db_backup_repository() -> str:
  return os.path.join(BACKUP_FOLDER, DB_BACKUP_REPOSITORY)


def fetch_backup(output_path: str, snapshot: str = 'latest', server=None):
  """Estrae un dump dal repository restic, pronto per data_import.

  `snapshot` e' l'id restic (`restic snapshots`) o `latest`. Il file scritto e'
  in chiaro: va cancellato appena importato.
  """
  if not BACKUP_FOLDER:
    raise ValueError('BACKUP_FOLDER non configurata')

  return download_db_dump(db_backup_repository(), DB_BACKUP_FILENAME, output_path, snapshot, server)


def check_local_disk_usage():
  """Blocca il backup quando il disco della macchina e' quasi pieno.

  Il dump nasce sempre qui, sul sistema operativo che ospita anche Postgres e
  gli altri servizi, e qui resta finche' non e' stato trasferito; senza `server`
  qui c'e' pure il ripiego, in BACKUP_FALLBACK_FOLDER. Riempire questo disco non
  fa perdere solo il backup ma la macchina, quindi sopra BACKUP_DISK_THRESHOLD
  si salta il giro e si avvisa, invece di produrre un dump che il disco non
  regge.
  """
  for path in local_disk_paths():
    used_percent, free = disk_usage(path)
    if used_percent < BACKUP_DISK_THRESHOLD:
      continue

    raise LocalDiskAlmostFullError(
      f'Disco locale al {used_percent:.1f}% su "{path}" '
      f'(soglia {BACKUP_DISK_THRESHOLD}%, {format_size(free)} liberi): dump non avviato.'
    )


def local_disk_paths() -> list:
  """Percorsi da controllare: dove finisce il dump e dove finirebbe il fallback.

  Sono quasi sempre lo stesso filesystem, ma il fallback puo' stare su un mount
  a parte. I duplicati si scartano per device, cosi' il controllo non ripete lo
  stesso disco due volte. La root del fallback serve per il caso in cui quel
  mount esista ma la sottocartella del progetto non sia ancora stata creata.
  """
  paths = []
  seen = set()

  for path in (os.getcwd(), BACKUP_FALLBACK_FOLDER, BACKUP_FALLBACK_ROOT):
    if not os.path.isdir(path):
      continue

    device = os.stat(path).st_dev
    if device in seen:
      continue

    seen.add(device)
    paths.append(path)

  return paths


def disk_usage(path: str) -> tuple:
  usage = shutil.disk_usage(path)
  return usage.used / usage.total * 100, usage.free


def format_size(size: int) -> str:
  return f'{size / 1024**3:.1f} GB'


def report_failed_backup(db_url: str, error: Exception, file_path: str = None, server=None):
  title = '**📦 DB Backup Fallito**'
  label = '**❌ Errore durante il backup'
  if isinstance(error, LocalDiskAlmostFullError):
    title = '**📦 DB Backup Bloccato — disco della macchina quasi pieno**'
    label = '**🛑 Backup non avviato'
  elif is_disk_full(error):
    title = '**📦 DB Backup Fallito — spazio esaurito**'

  message = [
    f'{title}\n▶️ `{mask_db_url(db_url)}`\n',
    f'{label} ({"server" if server else "local"}):**',
    f'`{error_details(error)}`',
  ]

  if file_path and os.path.exists(file_path):
    message.append(keep_dump(file_path, server))

  # Anche i dettagli dell'errore possono riportare la riga di comando di
  # pg_dump, quindi l'URL: si ripulisce il messaggio intero.
  send_telegram_message(hide_db_password('\n'.join(message), db_url))


def mask_db_url(db_url: str) -> str:
  """L'URL del database senza password, da mostrare nelle notifiche.

  La notifica serve a capire quale database non e' stato salvato: bastano
  utente, host e nome. La password non deve mai lasciare la macchina, e un
  canale Telegram non e' il posto dove tenerla.
  """
  try:
    parts = urlsplit(db_url)
    if parts.password is None:
      return db_url

    # Host e porta presi cosi' come sono scritti: `hostname` toglierebbe le
    # parentesi di un IPv6 ([::1]) e metterebbe l'host in minuscolo.
    host = parts.netloc.rpartition('@')[2]
    user = f'{parts.username}:***@' if parts.username else ':***@'
    return parts._replace(netloc=f'{user}{host}').geturl()
  except Exception:
    return '***'


def hide_db_password(text: str, db_url: str) -> str:
  """Toglie dal testo l'URL e la password del database, se compaiono.

  I messaggi d'errore di pg_dump e dei comandi di copia possono riportare la
  riga di comando, quindi l'URL intero: si sostituisce prima l'URL, poi la
  password da sola, nel caso compaia in un'altra forma.
  """
  if not text:
    return text

  text = text.replace(db_url, mask_db_url(db_url))
  try:
    password = urlsplit(db_url).password
  except Exception:
    password = None
  if password:
    # Nell'URL la password puo' essere percent-encoded (p%40ss), ma pg_dump e
    # libpq la stampano decodificata (p@ss): si nascondono tutte e due.
    for form in {password, unquote(password)}:
      text = text.replace(form, '***')
  return text


def keep_dump(file_path: str, server=None) -> str:
  """Mette al riparo il dump appena prodotto: e' l'unica copia esistente.

  La cartella di ripiego e' sempre quella della macchina che ospita i backup:
  con `server` e' quella remota, dove il dump sta accanto alla destinazione e si
  va a cercarlo per un restore; senza, e' questa macchina. Il disco che regge
  Postgres e gli altri servizi non e' un ripiego: se i backup vivono altrove, li'
  il dump non ci resta.

  Il dump poi non si muove piu': quando l'hdd torna ad avere spazio sono i backup
  nuovi a riprendere la strada giusta, i vecchi restano nel ripiego. Sono gia' al
  sicuro, e rimetterli in circolo vorrebbe dire trasferimenti e notifiche in piu'
  per un file che nessuno sta cercando li'.
  """
  try:
    where = 'sulla macchina di backup' if server else 'nella cartella di ripiego'
    return f'\n**💾 Dump tenuto {where}:** `{park_dump(file_path, server)}`'

  except Exception as e:
    return (
      f'\n**🛑 Dump non messo al sicuro:** `{BACKUP_FALLBACK_FOLDER}` non raggiungibile'
      f'\n`{error_details(e)}`'
      f'\nIl dump resta su questa macchina in `{file_path}`.'
    )


def park_dump(file_path: str, server=None) -> str:
  """Il ripiego e' anch'esso un repository restic: cifrato come la destinazione."""
  if not server:
    repository = os.path.join(BACKUP_FALLBACK_FOLDER, DB_BACKUP_REPOSITORY)
  else:
    repository = os.path.join(BACKUP_FALLBACK_ROOT, PROJECT_NAME, DB_BACKUP_REPOSITORY)

  fallback_path = upload_db_dump(file_path, repository, DB_BACKUP_FILENAME, server)
  os.remove(file_path)
  return fallback_path


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
  """Dimentica gli snapshot piu' vecchi di BACKUP_DAYS giorni e libera lo spazio.

  `--keep-within` conta i giorni a partire dallo snapshot piu' recente, non da
  oggi: se i backup si fermano, quelli rimasti non scadono uno dopo l'altro fino
  a lasciare il repository vuoto.
  """
  cleanup_db_dumps(db_backup_repository(), server)


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
