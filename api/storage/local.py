import os
import zipfile
import paramiko
from flask import request
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


def zip_folder_local(folder_path, dest_folder=None):
  zip_filename = os.path.basename(folder_path.rstrip('/\\')) + '.zip'

  if dest_folder:
    zip_path = os.path.join(dest_folder, zip_filename)
  else:
    zip_path = os.path.join(os.getcwd(), zip_filename)

  with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
    for root, dirs, files in os.walk(folder_path):
      for file in files:
        file_path = os.path.join(root, file)
        arcname = os.path.relpath(file_path, start=folder_path)
        zipf.write(file_path, arcname)
  return zip_path


def upload_large_file_to_pc(file_path, remote_host, remote_user, remote_path, password, port=22):
  ssh = paramiko.SSHClient()
  ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
  ssh.connect(remote_host, username=remote_user, port=port, password=password)

  sftp = ssh.open_sftp()

  try:
    remote_size = sftp.stat(remote_path).st_size
  except FileNotFoundError:
    remote_size = 0

  local_size = os.path.getsize(file_path)
  if remote_size > local_size:
    raise ValueError('Remote file is larger than local file!')

  with open(file_path, 'rb') as f:
    f.seek(remote_size)
    with sftp.file(remote_path, 'ab') as remote_file:
      while True:
        data = f.read(1024 * 1024 * 50)
        if not data:
          break
        remote_file.write(data)

  sftp.close()
  ssh.close()
  return f'{remote_user}@{remote_host}:{remote_path}'


def get_local_key(key):
  if IS_DEV is None:
    return key
  elif IS_DEV:
    return f'test/{key}'
  else:
    return f'prod/{key}'
