import os
import shutil
import tempfile
import subprocess

from .utils import get_local_key
from ..settings import BACKUP_SSH_CONFIG, RESTIC_PASSWORD, BACKUP_FOLDER, SERVER_NAME, RESTIC_PASSWORD_TEST


def storage_decorator(func):
  def wrapper(*args, **kwargs):
    if not BACKUP_SSH_CONFIG:
      raise ValueError('BACKUP_SSH_CONFIG non configurato')

    return func(*args, **kwargs)

  wrapper.__name__ = func.__name__
  return wrapper


@storage_decorator
def upload_file_server(content, filename, folder, subfolder=None):
  if subfolder:
    key = f'{subfolder}/{filename}'
  else:
    key = get_local_key(filename)

  remote_path = os.path.join(folder, key)

  subprocess.run(
    [
      'ssh',
      f'{BACKUP_SSH_CONFIG}',
      f'mkdir -p "{os.path.dirname(remote_path)}"',
    ],
    check=True,
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
        f'{BACKUP_SSH_CONFIG}:{remote_path}',
      ],
      check=True,
    )

  finally:
    if tmp_path and os.path.exists(tmp_path):
      os.remove(tmp_path)

  return remote_path


@storage_decorator
def delete_file_server(filename, folder, subfolder=None):
  if subfolder:
    key = os.path.join(folder, subfolder)
  elif folder:
    key = os.path.join(folder, get_local_key(''))
  else:
    key = folder

  subprocess.run(
    [
      'ssh',
      f'{BACKUP_SSH_CONFIG}',
      f'rm "{os.path.join(key, filename)}"',
    ],
    check=True,
  )


@storage_decorator
def list_files_server(folder, subfolder=None):
  if subfolder:
    key = subfolder
  else:
    key = f'{folder}/{get_local_key("")}'

  result = subprocess.run(
    [
      'ssh',
      f'{BACKUP_SSH_CONFIG}',
      f'find "{os.path.join(folder, key)}" -maxdepth 1 -type f -printf "%f\\n"',
    ],
    capture_output=True,
    text=True,
    check=True,
  )

  return [os.path.join(key, file) for file in result.stdout.strip().splitlines()]


@storage_decorator
def folder_backup_server(folder_to_backup):
  if not RESTIC_PASSWORD_TEST:
    raise ValueError('RESTIC_PASSWORD non configurata')

  env = os.environ.copy()
  env['RESTIC_PASSWORD'] = RESTIC_PASSWORD
  if not BACKUP_FOLDER:
    raise ValueError('BACKUP_FOLDER non configurata')

  if not SERVER_NAME:
    raise ValueError('SERVER_NAME non configurato')

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
    env=env,
    check=True,
  )
