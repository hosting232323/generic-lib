import os
import sys
import json
import requests

from database_api.backup import data_export, data_import
from api.storage.restricted_users import (
  list_user_backups,
  get_user_backup_file,
  get_user_backup_file_size,
  get_user_backup_info,
)


def db_export():
  data_export(sys.argv[1])


def db_import():
  data_import(sys.argv[1], sys.argv[2])


def setup_project():
  response = requests.get(f'https://fastsite.it/api/setup-project?project_type={sys.argv[1]}').json()
  if response['status'] == 'ko':
    raise Exception(response['error'])

  create_files_and_folders(response['setup'], '.')
  if not os.path.exists('.env'):
    print('You need to setup the file .env')  # noqa: T201


def create_files_and_folders(obj: dict, base_path: str):
  for key in obj.keys():
    path = os.path.join(base_path, key)
    if type(obj[key]) is dict:
      os.makedirs(path, exist_ok=True)
      create_files_and_folders(obj[key], path)
    elif type(obj[key]) is str:
      if os.path.exists(path):
        print(f'Already exists {path}')  # noqa: T201
      else:
        with open(path, 'w', encoding='utf-8') as file:
          file.write(obj[key])
          print(f'Generate file {path}')  # noqa: T201


def backup_list():
  """
  List all backup files for a restricted user.
  Usage: backup_list <username> [subfolder]
  """
  if len(sys.argv) < 2:
    print('Usage: backup_list <username> [subfolder]')  # noqa: T201
    sys.exit(1)

  username = sys.argv[1]
  subfolder = sys.argv[2] if len(sys.argv) > 2 else None

  try:
    info = get_user_backup_info(username)
    print(json.dumps(info, indent=2))  # noqa: T201
  except Exception as e:
    print(f'Error listing backups for {username}: {e}')  # noqa: T201
    sys.exit(1)


def backup_download():
  """
  Download a backup file for a restricted user.
  Usage: backup_download <username> <filename> [output_path]
  """
  if len(sys.argv) < 3:
    print('Usage: backup_download <username> <filename> [output_path]')  # noqa: T201
    sys.exit(1)

  username = sys.argv[1]
  filename = sys.argv[2]
  output_path = sys.argv[3] if len(sys.argv) > 3 else filename

  try:
    file_content = get_user_backup_file(username, filename)
    with open(output_path, 'wb') as f:
      f.write(file_content)
    size_mb = len(file_content) / (1024 * 1024)
    print(f'Downloaded {filename} ({size_mb:.2f} MB) to {output_path}')  # noqa: T201
  except FileNotFoundError:
    print(f'Backup file not found: {filename}')  # noqa: T201
    sys.exit(1)
  except Exception as e:
    print(f'Error downloading backup: {e}')  # noqa: T201
    sys.exit(1)


def backup_info():
  """
  Get detailed info about a user's backups.
  Usage: backup_info <username>
  """
  if len(sys.argv) < 2:
    print('Usage: backup_info <username>')  # noqa: T201
    sys.exit(1)

  username = sys.argv[1]

  try:
    info = get_user_backup_info(username)
    print(f'Backup Info for user: {username}')  # noqa: T201
    print(f'Total files: {info["total_files"]}')  # noqa: T201
    print(f'Total size: {info["total_size_mb"]} MB')  # noqa: T201
    print()  # noqa: T201
    print('Files:')  # noqa: T201
    for file in info['files']:
      print(f'  - {file["filename"]}: {file["size_mb"]} MB')  # noqa: T201
  except Exception as e:
    print(f'Error getting backup info: {e}')  # noqa: T201
    sys.exit(1)
