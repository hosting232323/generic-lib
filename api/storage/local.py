import os
import shutil
import subprocess
import tempfile

from .utils import set_backup_env
from ..settings import BACKUP_FOLDER, SERVER_NAME, BACKUP_DAYS


def _upload_file_local(content, full_path):
  directory = os.path.dirname(full_path) or '.'
  os.makedirs(directory, exist_ok=True)

  descriptor, temporary_path = tempfile.mkstemp(prefix='.generic-lib-upload-', dir=directory)
  try:
    with os.fdopen(descriptor, 'wb') as temporary_file:
      shutil.copyfileobj(content, temporary_file, length=1024 * 1024)
    os.replace(temporary_path, full_path)
  finally:
    if os.path.exists(temporary_path):
      os.remove(temporary_path)

  return full_path


def _delete_file_local(full_path):
  os.remove(full_path)


def _list_files_local(full_path, recursive=False):
  if not os.path.isdir(full_path):
    return []

  if recursive:
    return sorted(os.path.join(root, file) for root, _, files in os.walk(full_path) for file in files)

  return sorted(
    os.path.join(full_path, file) for file in os.listdir(full_path) if os.path.isfile(os.path.join(full_path, file))
  )


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


def _cleanup_folder_backups_local():
  subprocess.run(
    [
      'restic',
      '-r',
      os.path.join(BACKUP_FOLDER, 'folder-backup'),
      'forget',
      '--keep-daily',
      str(BACKUP_DAYS),
      '--prune',
    ],
    env=set_backup_env(),
    check=True,
    capture_output=True,
    text=True,
  )
