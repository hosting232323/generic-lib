import os
import subprocess

from .utils import get_full_path, set_backup_env
from ..settings import BACKUP_FOLDER, SERVER_NAME


def upload_file_local(content, filename, folder, subfolder=None, ignore_dev=None):
  full_path = get_full_path(folder, ignore_dev, subfolder, filename)
  os.makedirs(os.path.dirname(full_path), exist_ok=True)

  with open(full_path, 'wb') as file:
    file.write(content.read())
  return full_path


def delete_file_local(filename, folder, subfolder=None, ignore_dev=None):
  full_path = get_full_path(folder, ignore_dev, subfolder, filename)
  os.remove(full_path)


def list_files_local(folder, subfolder=None, ignore_dev=False):
  full_path = get_full_path(folder, ignore_dev, subfolder)
  return [
    os.path.join(full_path, file)
    for file in os.listdir(full_path)
    if os.path.isfile(os.path.join(full_path, file))
  ]


def folder_backup_local(folder_to_backup):
  subprocess.run(
    [
      'restic',
      '-r',
      os.path.join(BACKUP_FOLDER, 'folder-backup'),
      'backup',
      folder_to_backup,
      '--host',
      SERVER_NAME,
    ],
    env=set_backup_env(),
    check=True,
    capture_output=True,
    text=True,
  )
