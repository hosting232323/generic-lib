import os
from sqlalchemy import text
from database_api import set_database
from api.storage import list_files_in_s3

def get_user_input():
  db_url = input('Inserisci l\'URL del database: ')
  query = input('Inserisci la query per ottenere i file: ')
  bucket_name = input('Inserisci il nome del bucket S3: ')
  folder_input = input('Folder selezionato: (None, prod, test) (default: None): ') or 'None'
  return db_url, query, bucket_name, folder_input

def parse_is_dev(folder_input):

  folder_input = folder_input.lower()
  if folder_input == "none" or folder_input == "":
      return None
  elif folder_input == "test":
      return True
  elif folder_input == "prod":
      return False
  else:
      raise ValueError("Input non valido. Scegli tra 'None', 'prod', o 'test'.")

def normalize_filename(filename):
  filename = filename.strip()
  return filename

def get_db_files(db_url, query):
  with set_database(db_url).connect() as conn:
    result = conn.execute(text(query))
    return {normalize_filename(os.path.basename(row[0])) for row in result if row[0]}

def get_s3_files(bucket_name, is_dev=None):
  folder_prefix = ''
  if is_dev is not None:
      folder_prefix = 'test/' if is_dev else 'prod/'
  return {os.path.basename(url) for url in list_files_in_s3(bucket_name, folder=folder_prefix)}
    
def run_comparison():
  db_url, query, bucket_name, folder_input = get_user_input()
  is_dev = parse_is_dev(folder_input)

  db_files = get_db_files(db_url, query)
  s3_files = get_s3_files(bucket_name, is_dev)

  common_files = db_files.intersection(s3_files)
  only_in_s3 = s3_files - db_files
  only_in_db = db_files - s3_files
  
  print(f'\nFile presenti solo in S3 ({len(only_in_s3)}):')
  for file in sorted(only_in_s3):
      print(f"- {file}")
  
  print(f'\nFile presenti solo nel DB ({len(only_in_db)}):')
  for file in sorted(only_in_db):
      print(f"- {file}")
  
  # Salva risultati completi su file
  #with open('comparison_debug.txt', 'w') as f:
  #    f.write("NORMALIZED DB FILES:\n" + "\n".join(sorted(db_files)) + "\n\n")
  #    f.write("NORMALIZED S3 FILES:\n" + "\n".join(sorted(s3_files)) + "\n\n")
  #    f.write("ONLY IN DB:\n" + "\n".join(sorted(only_in_db)) + "\n\n")
  #    f.write("ONLY IN S3:\n" + "\n".join(sorted(only_in_s3)))

