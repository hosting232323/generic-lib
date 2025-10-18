import os
import sys
import subprocess
from datetime import datetime
from werkzeug.utils import secure_filename

from api.storage import upload_file_to_s3, delete_file_from_s3, list_files_in_s3


def data_export(db_url: str):
  filename = f'{datetime.now().strftime("%y%m%d%H%M%S")}.dump'
  subprocess.run([
    'pg_dump', f'--dbname={db_url}',
    '--blobs', '--clean', '-Fc',
    '--verbose', '-f', filename
  ], check=True)
  return filename


def data_import(db_url: str, filename: str):
  if not os.path.exists(filename):
    print(f'File non trovato: {filename}')
    sys.exit(1)

  subprocess.run([
    'pg_restore', f'--dbname={db_url}',
    '--verbose', '--clean',
    '--if-exists', '--no-privileges',
    '--no-owner', filename
  ], check=True)

  
def db_backup(db_url: str, sub_folder: str):
  zip_filename = data_export(db_url)
  s3_bucket = 'fastsite-postgres-backup'
  s3_key = f'{sub_folder}/{secure_filename(zip_filename)}'

  with open(zip_filename, 'rb') as file:
    upload_file_to_s3(file, s3_bucket, s3_key)
  os.remove(zip_filename)
  manage_s3_backups(s3_bucket, sub_folder)

  print(f'[{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}] Backup eseguito!')


def manage_s3_backups(bucket: str, sub_folder: str):
  backups = list_files_in_s3(bucket, sub_folder)  
  backups.sort()
  backup_days = int(os.environ.get('POSTGRES_BACKUP_DAYS', 14))

  if len(backups) > backup_days:
    files_to_delete = backups[:len(backups) - backup_days]
    for file_key in files_to_delete:
      delete_file_from_s3(bucket, file_key)
