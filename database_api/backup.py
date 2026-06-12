import os
import sys
import threading
import subprocess
from datetime import datetime

from api.telegram import send_telegram_message
from api.settings import POSTGRES_BACKUP_DAYS, BACKUP_FOLDER, POSTGRES_DOCKER_CONTAINER
from api.storage import upload_file, get_all_filenames, delete_file


PG_DUMP_FLAGS = ['--blobs', '--clean', '-Fc', '--verbose']
PG_RESTORE_FLAGS = ['--verbose', '--clean', '--if-exists', '--no-privileges', '--no-owner']


def data_export(db_url: str):
  filename = f'{datetime.now().strftime("%y%m%d%H%M%S")}.dump'

  if POSTGRES_DOCKER_CONTAINER:
    _docker_pg_dump(db_url, filename)
  else:
    _local_pg_dump(db_url, filename)

  return filename


def data_import(db_url: str, filename: str):
  if not os.path.exists(filename):
    print(f'File non trovato: {filename}')  # noqa: T201
    sys.exit(1)

  if POSTGRES_DOCKER_CONTAINER:
    _docker_pg_restore(db_url, filename)
  else:
    _local_pg_restore(db_url, filename)


def db_backup(db_url: str, storage_type):
  def run():
    try:
      if not BACKUP_FOLDER:
        raise ValueError('BACKUP_FOLDER non configurata')

      filename = data_export(db_url)
      with open(filename, 'rb') as content:
        upload_file(content, filename, BACKUP_FOLDER, storage_type, 'postgres-backup', True)
      delete_file(filename, '', 'local', ignore_dev=True)

      backups = get_all_filenames(BACKUP_FOLDER, storage_type, 'postgres-backup', True)
      dump_files = [f for f in backups if f.lower().endswith('.dump')]
      dump_files.sort()
      if len(dump_files) > POSTGRES_BACKUP_DAYS:
        files_to_delete = dump_files[: len(dump_files) - POSTGRES_BACKUP_DAYS]
        for file_to_delete in files_to_delete:
          filename = os.path.basename(file_to_delete)
          subfolder_path = os.path.dirname(file_to_delete) or None

          delete_file(filename, BACKUP_FOLDER, storage_type, subfolder_path, True)

    except subprocess.CalledProcessError as e:
      send_telegram_message(
        '\n'.join(
          [
            f'*📦 DB Backup Fallito*\n▶️ `{db_url}`\n',
            f'*❌ Errore durante il backup ({storage_type}):*',
            f'`{e.stderr.strip() or e.stdout.strip() or str(e)}`',
          ]
        )
      )

  thread = threading.Thread(target=run, daemon=True)
  thread.start()


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
