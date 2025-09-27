import os
import sys
import subprocess
from datetime import datetime

# Gestire la raw connection con un decorator

def data_export_():
  db_url = sys.argv[1]
  output_file = f'{datetime.now().strftime("%y%m%d%H%M%S")}.sql'

  cmd = [
    "pg_dump",
    f"--dbname={db_url}",
    "--blobs",
    "-f", output_file
  ]
  try:
    subprocess.run(cmd, check=True)
    print(f"Export completato: {output_file}")
  except subprocess.CalledProcessError as e:
    print("Errore durante l'export:", e)
    sys.exit(1)


def data_import_():
  db_url = sys.argv[1]
  input_file = sys.argv[2]

  if not os.path.exists(input_file):
    print(f"File non trovato: {input_file}")
    sys.exit(1)

  cmd = [
    "psql",
    f"--dbname={db_url}",
    "-f", input_file
  ]
  try:
    subprocess.run(cmd, check=True)
    print(f"Import completato da {input_file}")
  except subprocess.CalledProcessError as e:
    print("Errore durante l'import:", e)
    sys.exit(1)
