import os
import sys
import subprocess
from datetime import datetime

from api.settings import POSTGRES_BACKUP_DAYS
from api.storage import upload_file, get_all_filenames, delete_file
from api.settings import BACKUP_FOLDER


def data_export(db_url: str):
  filename = f'{datetime.now().strftime("%y%m%d%H%M%S")}.dump'
  subprocess.run(
    ['pg_dump', f'--dbname={db_url}', '--blobs', '--clean', '-Fc', '--verbose', '-f', filename], check=True
  )
  return filename


def data_import(db_url: str, filename: str):
  if not os.path.exists(filename):
    print(f'File non trovato: {filename}')  # noqa: T201
    sys.exit(1)

  subprocess.run(
    [
      'pg_restore',
      f'--dbname={db_url}',
      '--verbose',
      '--clean',
      '--if-exists',
      '--no-privileges',
      '--no-owner',
      filename,
    ],
    check=True,
  )


def db_backup(db_url: str, storage_type):
  if not BACKUP_FOLDER:
    raise ValueError('BACKUP_FOLDER non configurata')
  
  filename = data_export(db_url)
  with open(filename, 'rb') as content:
    file_url = upload_file(content, filename, BACKUP_FOLDER, storage_type, 'postgres-backup')
  delete_file(filename, '', 'local')

  backups = get_all_filenames(BACKUP_FOLDER, storage_type, 'postgres-backup')
  dump_files = [f for f in backups if f.lower().endswith('.dump')]
  dump_files.sort()
  if len(dump_files) > POSTGRES_BACKUP_DAYS:
    files_to_delete = dump_files[: len(dump_files) - POSTGRES_BACKUP_DAYS]
    for file_to_delete in files_to_delete:
      filename = os.path.basename(file_to_delete)
      subfolder_path = os.path.dirname(file_to_delete) or None

      delete_file(filename, BACKUP_FOLDER, storage_type, subfolder_path)

  return {'status': 'ok', 'message': 'Backup eseguito correttamente', 'file_url': file_url}
