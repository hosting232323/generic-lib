import os
import sys
import subprocess
from datetime import datetime

from api.storage import db_backup_s3, db_backup_local


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


def db_backup(db_url: str, folder: str, storage):
  zip_filename = data_export(db_url)
  if storage == 'hdd':
    db_backup_local(zip_filename, folder)
  elif storage == 's3':
    db_backup_s3(zip_filename, folder)
