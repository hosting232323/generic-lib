import os
import sys
import subprocess
from datetime import datetime


def data_export_(db_url: str): 
  subprocess.run([
    'pg_dump',
    f'--dbname={db_url}',
    '--blobs',
    '-f', f'{datetime.now().strftime("%y%m%d%H%M%S")}.sql'
  ], check=True)


def data_import_(db_url: str, input_file: str):
  if not os.path.exists(input_file):
    print(f'File non trovato: {input_file}')
    sys.exit(1)

  subprocess.run([
    'psql',
    f'--dbname={db_url}',
    '-f', input_file
  ], check=True)
