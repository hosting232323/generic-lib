import os
import subprocess

from .utils import get_local_key, set_backup_env
from ..settings import BACKUP_FOLDER, SERVER_NAME


def upload_file_local(content, filename, folder, subfolder=None, ignore_dev=None):
  if ignore_dev:
    key = filename
  else:
    key = get_local_key(filename)

  if subfolder:
    key = f'{subfolder}/{key}'

  full_path = os.path.join(folder, key)
  os.makedirs(os.path.dirname(full_path), exist_ok=True)

  with open(full_path, 'wb') as file:
    file.write(content.read())
  return full_path


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


def folder_backup_local(folder_to_backup):
  subprocess.run(
    ['restic', '-r', os.path.join(BACKUP_FOLDER, 'folder-backup'), 'backup', folder_to_backup, '--host', SERVER_NAME],
    env=set_backup_env(),
    check=True,
    capture_output=True,
    text=True,
  )
