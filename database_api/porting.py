import os
import sys
import subprocess
from datetime import datetime


def data_export(db_url: str):
  filename = f'{datetime.now().strftime("%y%m%d%H%M%S")}.dump'
  subprocess.run(['pg_dump', f'--dbname={db_url}', '--blobs', '--clean', '-Fc', '-f', filename], check=True)
  return filename


def data_import(db_url: str, file_path: str):
  if not os.path.exists(file_path):
    print(f'File non trovato: {file_path}')
    sys.exit(1)

  subprocess.run(
    ['pg_restore', f'--dbname={db_url}', '--verbose', '--clean', '--if-exists', '--no-privileges', file_path],
    check=True,
  )
