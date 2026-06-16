import os
import subprocess

from .utils import set_backup_env
from ..settings import BACKUP_FOLDER, SERVER_NAME


def _upload_file_local(content, full_path):
  os.makedirs(os.path.dirname(full_path), exist_ok=True)

  with open(full_path, 'wb') as file:
    file.write(content.read())
  return full_path


def _delete_file_local(full_path):
  os.remove(full_path)


def _list_files_local(full_path):
  return [
    os.path.join(full_path, file) for file in os.listdir(full_path) if os.path.isfile(os.path.join(full_path, file))
  ]


def _folder_backup_local(folder_to_backup):
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
