import os
import subprocess

from ..settings import SFTP_USER, SFTP_HOST


def folder_backup(repo_path, folder, password, server_name):
  env = os.environ.copy()
  env['RESTIC_PASSWORD'] = password
  if SFTP_USER:
    repo_path = f'sftp:{SFTP_USER}@{SFTP_HOST}:{repo_path}'

  subprocess.run(['restic', '-r', repo_path, 'backup', folder, '--host', server_name], env=env, check=True)


def send_file_or_folder(file_folder, remote_path):
  subprocess.run(
    ['rsync', '-avz', '--partial', '--progress', '--append-verify', file_folder, f'{SFTP_USER}@{SFTP_HOST}:{remote_path}'],
    check=True,
  )
