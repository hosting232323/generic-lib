import os
from datetime import datetime
from werkzeug.utils import secure_filename
from apscheduler.schedulers.background import BackgroundScheduler

from .porting import data_export_
from api.storage import upload_file_to_s3, delete_file_from_s3, list_files_in_s3


def get_project_folder():
  return os.path.basename(os.getcwd())


def schedule_backup(engine):
  scheduler = BackgroundScheduler()
  scheduler.add_job(lambda: db_backup(engine), 'interval', days=1)
  scheduler.start()
  
  
def db_backup(engine):
  zip_filename = data_export_(engine)
  s3_bucket = 'fastsite-postgres-backup'
  s3_folder = get_project_folder()
  s3_key = f'{s3_folder}/{secure_filename(zip_filename)}'

  with open(zip_filename, 'rb') as file:
    upload_file_to_s3(file, s3_bucket, s3_key)
  os.remove(zip_filename)
  manage_s3_backups(s3_bucket, s3_folder)

  print(f'[{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}] Backup eseguito!')


def manage_s3_backups(bucket, folder):
  backups = list_files_in_s3(bucket, folder)  
  backups.sort()
  backup_days = os.environ.get('POSTGRES_BACKUP_DAYS', 14)

  if len(backups) > backup_days:
    files_to_delete = backups[:len(backups) - backup_days]
    for file_key in files_to_delete:
      delete_file_from_s3(bucket, file_key)
