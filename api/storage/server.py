import os
import subprocess

from ..settings import SFTP_USER, SFTP_HOST, RESTIC_PASSWORD, BACKUP_FOLDER, SERVER_NAME


def folder_backup_server(folder_to_backup):
  env = os.environ.copy()

  if not RESTIC_PASSWORD:
    raise ValueError('RESTIC_PASSWORD non configurata')
  env['RESTIC_PASSWORD'] = RESTIC_PASSWORD

  if not SFTP_USER:
    raise ValueError('SFTP_USER non configurato')

  if not SFTP_HOST:
    raise ValueError('SFTP_HOST non configurato')

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


def send_file_or_folder_server(file_folder, remote_path):
  subprocess.run(
    [
      'rsync',
      '-avz',
      '--partial',
      '--progress',
      '--append-verify',
      file_folder,
      f'{SFTP_USER}@{SFTP_HOST}:{remote_path}',
    ],
    check=True,
  )
