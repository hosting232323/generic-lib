import time
import schedule
import threading
from datetime import datetime
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def job():
    logging.info(f"Backup job executed at {datetime.now()}")

def scheduler_thread():
    while True:
        schedule.run_pending()
        time.sleep(1)  # Check every second for pending jobs

def schedule_backup():
    logging.info("Scheduling the job.")
    schedule.every().day.at("00:00").do(job)  # Schedule the job to run every day at midnight
    logging.info("Job scheduled to run every day at midnight.")
    
    scheduler_thread_instance = threading.Thread(target=scheduler_thread)
    scheduler_thread_instance.daemon = True
    scheduler_thread_instance.start()
    logging.info("Scheduler thread started.")

def start_scheduler():
    logging.info("Starting scheduler.")
    # Execute the job immediately for the first time
    logging.info("Executing the job immediately for the first run.")
    job()
    
    # Start the schedule for subsequent runs
    schedule_backup()

# Start the scheduler with
#start_scheduler()
