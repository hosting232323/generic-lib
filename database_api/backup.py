import os
import sys
import subprocess
from datetime import datetime

from api.storage import upload_file, get_all_filenames, delete_file


POSTGRES_BACKUP_DAYS = int(os.environ.get('POSTGRES_BACKUP_DAYS', 14))


def data_export(db_url: str):
  filename = f'{datetime.now().strftime("%y%m%d%H%M%S")}.dump'
  subprocess.run(
    ['pg_dump', f'--dbname={db_url}', '--blobs', '--clean', '-Fc', '--verbose', '-f', filename], check=True
  )
  return filename


def data_import(db_url: str, filename: str):
  if not os.path.exists(filename):
    print(f'File non trovato: {filename}')
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


def db_backup(db_url: str, folder: str, storage_type, subfolder: str = None):
  filename = data_export(db_url)
  with open(filename, 'rb') as content:
    file_url = upload_file(content.read() if storage_type == 'local' else content, filename, folder, subfolder, storage_type)
  delete_file(filename, '', 'local')

  backups = get_all_filenames(folder, storage_type)
  backups.sort()
  if len(backups) > POSTGRES_BACKUP_DAYS:
    files_to_delete = backups[: len(backups) - POSTGRES_BACKUP_DAYS]
    for file_to_delete in files_to_delete:
      delete_file(file_to_delete, folder, storage_type)

  return {'status': 'ok', 'message': 'Backup eseguito correttamente', 'file_url': file_url }
