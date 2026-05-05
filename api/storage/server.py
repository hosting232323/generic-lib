import os
import subprocess

from ..settings import SFTP_USER, SFTP_HOST, RESTIC_PASSWORD, BACKUP_FOLDER, SERVER_NAME


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
