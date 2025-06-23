import os
from sqlalchemy import text
from database_api import set_database
from api.storage import list_files_in_s3


def get_user_input():
  return input('Inserisci l\'URL del database: '), \
    input('Inserisci la query per ottenere i file: '), \
    input('Inserisci il nome del bucket S3: '), \
    input('Folder selezionato: (None, prod, test) (default: None): ') or 'None'


def parse_is_dev(folder_input):
  folder_input = folder_input.lower()
  if folder_input == 'none' or folder_input == '':
    return None
  elif folder_input == 'test':
    return True
  elif folder_input == 'prod':
    return False
  else:
    raise ValueError('Input non valido. Scegli tra "None", "prod", o "test".')


def get_db_files(db_url, query):
  with set_database(db_url).connect() as conn:
    result = conn.execute(text(query))
    return {os.path.basename(row[0]).strip() for row in result if row[0]}


def get_s3_files(bucket_name, is_dev=None):
  folder_prefix = ''
  if is_dev is not None:
    folder_prefix = 'test/' if is_dev else 'prod/'
  return {os.path.basename(url) for url in list_files_in_s3(bucket_name, folder=folder_prefix)}

 
def check_aws_mismatch_(db_url, query, bucket_name, folder_input):
  db_files = get_db_files(db_url, query)
  s3_files = get_s3_files(bucket_name, parse_is_dev(folder_input))

  only_in_s3 = s3_files - db_files
  print(f'\nFile presenti solo in S3 ({len(only_in_s3)}):')
  for file in sorted(only_in_s3):
    print(f'- {file}')

  only_in_db = db_files - s3_files
  print(f'\nFile presenti solo nel DB ({len(only_in_db)}):')
  for file in sorted(only_in_db):
    print(f'- {file}')
    
  return {
    "only_in_s3": only_in_s3,
    "only_in_db": only_in_db
}
