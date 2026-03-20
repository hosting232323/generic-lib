import os
from flask import request
from ..settings import IS_DEV, API_PREFIX
from .utils import get_db_files
from ..telegram import send_telegram_message


def upload_file_local(content, filename, folder, subfolder=None):
  if subfolder:
    key = f'{subfolder}/{filename}'
  else:
    key = get_local_key(filename)

  full_path = os.path.join(folder, key)
  os.makedirs(os.path.dirname(full_path), exist_ok=True)

  with open(full_path, 'wb') as file:
    file.write(content.read())
  return f'http{"s" if not IS_DEV else ""}://{request.host}{f"/{API_PREFIX}" if API_PREFIX else ""}/photos/{key}'


def delete_file_local(filename, folder, subfolder=None):
  if subfolder:
    key = os.path.join(folder, subfolder)
  elif folder:
    key = os.path.join(folder, get_local_key(''))
  else:
    key = folder
  os.remove(os.path.join(key, filename))


def list_files_local(folder, subfolder=None):
  if subfolder:
    key = subfolder
  else:
    key = f'{folder}/{get_local_key("")}'

  full_path = os.path.join(folder, key)
  return [os.path.join(key, file) for file in os.listdir(full_path) if os.path.isfile(os.path.join(full_path, file))]


def check_mismatch_local(db_url, query, folder, subfolder):
  db_files = get_db_files(db_url, query)
  local_files = {os.path.basename(url) for url in list_files_local(folder, subfolder)}
  
  only_in_local = local_files - db_files

  message_lines = ['*📊 Report Check Mismatch Photos*\n']
  only_in_local = local_files - db_files
  message_lines.append(f'\n*❌ File presenti solo in locale ({len(only_in_local)}):*')
  if only_in_local:
    for file in sorted(only_in_local):
      message_lines.append(f'- {file}')
  else:
    message_lines.append('✔️ Nessun file solo in locale.')

  only_in_db = db_files - local_files
  message_lines.append(f'\n*❌ File presenti solo nel DB ({len(only_in_db)}):*')
  if only_in_db:
    for file in sorted(only_in_db):
      message_lines.append(f'- {file}')
  else:
    message_lines.append('✔️ Nessun file solo in s3.')

  message = '\n'.join(message_lines)
  send_telegram_message(message)


def get_local_key(key):
  if IS_DEV is None:
    return key
  elif IS_DEV:
    return f'test/{key}'
  else:
    return f'prod/{key}'
