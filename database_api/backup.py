import os

from api.storage import upload_file_to_s3, delete_file_from_s3, list_files_in_s3
from .porting import data_export_
from werkzeug.utils import secure_filename
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime


def get_project_folder():
  return os.path.basename(os.getcwd())


def schedule_backup(engine):
  scheduler = BackgroundScheduler()
  scheduler.add_job(lambda: db_backup(engine), "interval", days=1)    # Ogni giorno
  scheduler.start()
  
  
def db_backup(engine):
  timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
  print(f"[{timestamp}] Backup eseguito!")
  
  try:
    zip_filename = data_export_(engine)
    
    s3_bucket = 'fastsite-postgres-backup'
    s3_folder = get_project_folder()
    s3_key = f"{s3_folder}/{secure_filename(zip_filename)}"
    
    with open(zip_filename, "rb") as file:
      upload_file_to_s3(file, s3_bucket, s3_key)
  
    os.remove(zip_filename)
    
    manage_s3_backups(s3_bucket, s3_folder)
    
  except Exception as e:
    print(f"Errore durante il backup: {e}")

def manage_s3_backups(bucket, folder):
  try:
    backups = list_files_in_s3(bucket, folder)  
    backups.sort()
    
    if len(backups) > 14:
      files_to_delete = backups[:len(backups) - 14]  # Prende i più vecchi in eccesso
      for file_key in files_to_delete:
        delete_file_from_s3(bucket, file_key)
        print(f"Eliminato vecchio backup: {file_key}")

  except Exception as e:
    print(f"Errore nella gestione dei backup su S3: {e}")
