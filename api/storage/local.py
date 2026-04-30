import os
import zipfile
import paramiko
import subprocess
from flask import request
from datetime import datetime

from ..settings import IS_DEV, API_PREFIX


def upload_file_local(content, filename, folder, subfolder=None):
  if subfolder:
    key = f'{subfolder}/{filename}'
  else:
    key = get_local_key(filename)

  full_path = os.path.join(folder, key)
  os.makedirs(os.path.dirname(full_path), exist_ok=True)

  with open(full_path, 'wb') as file:
    file.write(content.read())
  return f'http{"s" if not IS_DEV else ""}://{request.host}{f"/{API_PREFIX}" if API_PREFIX else ""}/photos/{key}'


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


def folder_backup(repo_path, folder, password, server_name, sftp_user=None, sftp_host=None):
  env = os.environ.copy()
  env['RESTIC_PASSWORD'] = password
  if sftp_user:
    repo_path = f'sftp:{sftp_user}@{sftp_host}:{repo_path}'

  subprocess.run(['restic', '-r', repo_path, 'backup', folder, '--host', server_name], env=env, check=True)


def send_file_or_folder(file_folder, remote_path, user, host):
  subprocess.run([
    "rsync",
    "-avz",
    "--partial",
    "--progress",
    "--append-verify",
    file_folder,
    f"{user}@{host}:{remote_path}"
  ], check=True)


def get_local_key(key):
  if IS_DEV is None:
    return key
  elif IS_DEV:
    return f'test/{key}'
  else:
    return f'prod/{key}'
