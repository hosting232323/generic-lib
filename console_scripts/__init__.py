import os
import sys
import requests

from database_api.backup import data_export, data_import


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
        with open(path, 'w') as file:
          file.write(obj[key])
          print(f'Generate file {path}')  # noqa: T201
