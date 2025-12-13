import os
import sys
import subprocess
from datetime import datetime

from api.storage import upload_file, manage_backups
from werkzeug.utils import secure_filename


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


def db_backup(db_url: str, folder: str, storage_type):
  zip_filename = data_export(db_url)
  upload_file(storage_type, zip_filename, folder)
  manage_backups(storage_type, folder, bucket=s3_bucket, local_folder=folder)
