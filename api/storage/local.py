import os
import zipfile
from flask import request
from ..settings import IS_DEV, API_PREFIX


def upload_file_local(content, filename, folder, subfolder=None):
  if subfolder:
    key = f'{subfolder}/{filename}'
  else:
    key = get_local_key(filename)

  full_path = os.path.join(folder, key)
  os.makedirs(os.path.dirname(full_path), exist_ok=True)

  with open(full_path, 'wb') as file:
    file.write(content)
  return f'http{"s" if not IS_DEV else ""}://{request.host}{f"/{API_PREFIX}" if API_PREFIX else ""}/photos/{key}'


def delete_file_local(filename, folder, subfolder=None):
  if subfolder:
    key = subfolder
  elif folder:
    key = f'{folder}/{get_local_key("")}'
  else:
    key = folder
  os.remove(os.path.join(key, filename))


def list_files_local(folder, subfolder=None):
  if subfolder:
    key = subfolder
  else:
    key = f'{folder}/{get_local_key("")}'

  return [os.path.join(key, file) for file in os.listdir(key) if os.path.isfile(os.path.join(key, file))]


def zip_folder_local(folder_path, dest_folder=None):
  zip_filename = os.path.basename(folder_path.rstrip("/\\")) + '.zip'
  
  if dest_folder:
    zip_path = os.path.join(dest_folder, zip_filename)
  else:
    zip_path = os.path.join(os.getcwd(), zip_filename)

  with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
    for root, dirs, files in os.walk(folder_path):
      for file in files:
        file_path = os.path.join(root, file)
        arcname = os.path.relpath(file_path, start=folder_path)
        zipf.write(file_path, arcname)
  return zip_path


def get_local_key(key):
  if IS_DEV is None:
    return key
  elif IS_DEV:
    return f'test/{key}'
  else:
    return f'prod/{key}'
