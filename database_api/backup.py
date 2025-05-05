import os
from datetime import datetime
from sqlalchemy import Engine
from werkzeug.utils import secure_filename
from apscheduler.schedulers.background import BackgroundScheduler

from .porting import data_export_
from api.storage import upload_file_to_s3, delete_file_from_s3, list_files_in_s3

  
def db_backup(engine: Engine, sub_folder: str):
  zip_filename = data_export_(engine)
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
