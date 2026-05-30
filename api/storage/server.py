import os
import shutil
import tempfile
import subprocess

from .utils import get_full_path, set_backup_env
from ..settings import BACKUP_SSH_CONFIG, BACKUP_FOLDER, SERVER_NAME


def storage_decorator(func):
  def wrapper(*args, **kwargs):
    if not BACKUP_SSH_CONFIG:
      raise ValueError('BACKUP_SSH_CONFIG non configurato')

    return func(*args, **kwargs)

  wrapper.__name__ = func.__name__
  return wrapper


@storage_decorator
def upload_file_server(content, filename, folder, subfolder=None, ignore_dev=None):
  full_path = get_full_path(folder, subfolder, ignore_dev, filename)
  subprocess.run(
    [
      'ssh',
      f'{BACKUP_SSH_CONFIG}',
      f'mkdir -p "{os.path.dirname(full_path)}"',
    ],
    check=True,
    capture_output=True,
    text=True,
  )

  tmp_path = None
  try:
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
      shutil.copyfileobj(content, tmp)
      tmp_path = tmp.name

    subprocess.run(
      [
        'rsync',
        '-avz',
        '--partial',
        '--append-verify',
        tmp_path,
        f'{BACKUP_SSH_CONFIG}:{full_path}',
      ],
      check=True,
      capture_output=True,
      text=True,
    )

  finally:
    if tmp_path and os.path.exists(tmp_path):
      os.remove(tmp_path)

  return full_path


@storage_decorator
def delete_file_server(filename, folder, subfolder=None, ignore_dev=False):
  full_path = get_full_path(folder, subfolder, ignore_dev, filename)
  subprocess.run(
    [
      'ssh',
      f'{BACKUP_SSH_CONFIG}',
      f'rm "{full_path}"',
    ],
    check=True,
    capture_output=True,
    text=True,
  )


@storage_decorator
def list_files_server(folder, subfolder=None, ignore_dev=False):
  full_path = get_full_path(folder, subfolder, ignore_dev)
  return [
    os.path.join(full_path, file)
    for file in subprocess.run(
      [
        'ssh',
        f'{BACKUP_SSH_CONFIG}',
        f'find "{full_path}" -maxdepth 1 -type f -printf "%f\\n"',
      ],
      capture_output=True,
      text=True,
      check=True,
    )
    .stdout.strip()
    .splitlines()
  ]


@storage_decorator
def folder_backup_server(folder_to_backup):
  subprocess.run(
    [
      'restic',
      '-r',
      f'sftp:{BACKUP_SSH_CONFIG}:{os.path.join(BACKUP_FOLDER, "folder-backup")}',
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
