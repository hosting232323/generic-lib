import os
import sys
import threading
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


def db_backup(db_url: str, folder: str, storage_type, subfolder: str = None):
  def _backup_job():
    try:
      filename = data_export(db_url)

      with open(filename, 'rb') as content:
        upload_file(content, filename, folder, storage_type, subfolder)

      delete_file(filename, '', 'local')

      backups = get_all_filenames(folder, storage_type, subfolder)
      dump_files = [f for f in backups if f.lower().endswith('.dump')]
      dump_files.sort()

      if len(dump_files) > POSTGRES_BACKUP_DAYS:
        files_to_delete = dump_files[: len(dump_files) - POSTGRES_BACKUP_DAYS]

        for file_to_delete in files_to_delete:
          filename = os.path.basename(file_to_delete)
          subfolder_path = os.path.dirname(file_to_delete) or None

          delete_file(filename, folder, storage_type, subfolder_path)

    except Exception as e:
      print(f'[db_backup ERROR] {e}') # noqa: T201

  thread = threading.Thread(target=_backup_job, daemon=True)
  thread.start()

  return {'status': 'ok', 'message': 'Backup avviato in background'}
