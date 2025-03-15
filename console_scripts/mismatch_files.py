import os
from sqlalchemy import text

from database_api import set_database
from api.storage import list_files_in_s3


def get_user_input():
  return input('Inserisci l\'URL del database: '), \
    input('Inserisci la query per ottenere i file: '), \
    input('Inserisci il nome del bucket S3: ')


def get_db_files(db_url, query):
  with set_database(db_url).connect() as conn:
    result = conn.execute(text(query))
    return {os.path.basename(url) for url in {row[0] for row in result}}


def get_s3_files(bucket_name):
  return {os.path.basename(url) for url in list_files_in_s3(bucket_name)}


def run_comparison():
  db_url, query, bucket_name = get_user_input()
  db_files = get_db_files(db_url, query)
  s3_files = get_s3_files(bucket_name)

  only_in_s3 = s3_files - db_files
  only_in_db = db_files - s3_files

  print('File presenti solo in S3:', only_in_s3)
  print('File presenti solo nel DB:', only_in_db)