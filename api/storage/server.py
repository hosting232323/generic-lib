import os
import subprocess

from ..settings import IS_DEV, SFTP_USER, SFTP_HOST, RESTIC_PASSWORD, BACKUP_FOLDER, SERVER_NAME


def storage_decorator(func):
  def wrapper(*args, **kwargs):
    if not SFTP_USER:
      raise ValueError('SFTP_USER non configurato')

    if not SFTP_HOST:
      raise ValueError('SFTP_HOST non configurato')

    return func(*args, **kwargs)

  wrapper.__name__ = func.__name__
  return wrapper


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
      f'{SFTP_USER}@{SFTP_HOST}',
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
      f'{SFTP_USER}@{SFTP_HOST}',
      f'find "{os.path.join(folder, key)}" -maxdepth 1 -type f -printf "%f\\n"',
    ],
    capture_output=True,
    text=True,
    check=True,
  )

  return [os.path.join(key, file) for file in result.stdout.strip().splitlines()]


@storage_decorator
def folder_backup_server(folder_to_backup):
  env = os.environ.copy()

  if not RESTIC_PASSWORD:
    raise ValueError('RESTIC_PASSWORD non configurata')
  env['RESTIC_PASSWORD'] = RESTIC_PASSWORD

  if not BACKUP_FOLDER:
    raise ValueError('BACKUP_FOLDER non configurata')

  if not SERVER_NAME:
    raise ValueError('SERVER_NAME non configurato')

  subprocess.run(
    [
      'restic',
      '-r',
      f'sftp:{SFTP_USER}@{SFTP_HOST}:{os.path.join(BACKUP_FOLDER, "folder-backup")}',
      'backup',
      folder_to_backup,
      '--host',
      SERVER_NAME,
    ],
    env=env,
    check=True,
  )


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
      f'{SFTP_USER}@{SFTP_HOST}',
      f'mkdir -p "{os.path.dirname(remote_path)}"',
    ],
    check=True,
  )

  subprocess.run(
    [
      'rsync',
      '-avz',
      '--partial',
      '--append-verify',
      content,
      f'{SFTP_USER}@{SFTP_HOST}:{remote_path}',
    ],
    check=True,
  )

  return remote_path


def get_local_key(key):
  if IS_DEV is None:
    return key
  elif IS_DEV:
    return f'test/{key}'
  else:
    return f'prod/{key}'
