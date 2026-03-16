import os
from sqlalchemy import text
from database_api import set_database


def get_db_files(db_url, query):
  with set_database(db_url).connect() as conn:
    result = conn.execute(text(query))
    return {os.path.basename(row[0]).strip() for row in result if row[0]}


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
