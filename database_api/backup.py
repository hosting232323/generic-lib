import time
import schedule
import threading
from datetime import datetime, timedelta


def schedule_backup():
  threading.Timer(get_delay(), schedule_daily_job).start()


def job():
  print("La funzione è stata eseguita alle 4:20")


def get_delay() -> float:
  now = datetime.now()
  next_run = now.replace(hour=4, minute=20, second=0, microsecond=0)
  if now > next_run:
    next_run += timedelta(days=1)
  return (next_run - now).total_seconds()


def scheduler_thread():
  while True:
    schedule.run_pending()
    time.sleep(3600)


def schedule_daily_job():
  schedule.every().day.at("04:20").do(job)
  scheduler_thread = threading.Thread(target=scheduler_thread)
  scheduler_thread.daemon = True
  scheduler_thread.start()
