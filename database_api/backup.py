import os

from api.storage import upload_file_to_s3
from .porting import data_export_
from werkzeug.utils import secure_filename
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime


def get_project_folder():
  return os.path.basename(os.getcwd())


def schedule_backup(engine):
  scheduler = BackgroundScheduler()
  
  scheduler.add_job(lambda: db_backup("Giornaliero", engine), "interval", days=1)    # Ogni giorno
  scheduler.add_job(lambda: db_backup("Settimanale", engine), "interval", weeks=1)   # Ogni settimana
  scheduler.add_job(lambda: db_backup("Mensile", engine), "cron", day=1, hour=0, minute=0)  # Ogni 1° del mese a mezzanotte
  
  scheduler.start()
  
  
def db_backup(interval, engine):
  timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
  print(f"[{timestamp}] Backup eseguito! (Intervallo: {interval})")
  
  try:
    zip_filename = data_export_(engine)
    new_zip_filename = f"{interval.lower()}-{zip_filename}"
    os.rename(zip_filename, new_zip_filename)
    
    s3_key = f"{get_project_folder()}/{secure_filename(new_zip_filename)}"
    
    with open(new_zip_filename, "rb") as file:
      upload_file_to_s3(file, 'fastsite-postgres-backup', s3_key)
      
    os.remove(new_zip_filename)
    
  except Exception as e:
    print(f"Errore durante il backup: {e}")
