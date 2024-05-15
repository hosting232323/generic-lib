import os
import requests


url = 'https://genericbackend.replit.app/setup-project'


def setup_project_(generic_api_key):
  create_files_and_folders(requests.get(url, headers={
    'Authorization': generic_api_key
  }).json()['setup'], '.')
  if not os.path.exists('.env'):
    print('you need to setup the file .env')


def create_files_and_folders(obj: dict, base_path: str):
  for key in obj.keys():
    path = os.path.join(base_path, key)
    if type(obj[key]) is dict:
      os.makedirs(path, exist_ok=True)
      create_files_and_folders(obj[key], path)
    elif type(obj[key]) is str:
      if os.path.exists(path):
        print(f'not generate_file {path}')
      else:
        with open(path, 'w') as file:
          file.write(obj[key])
          print(f'generate file {path}')
