import os
import sys
import requests


hostname = (
  'https://generic-be.replit.app/'
  if len(sys.argv) > 2 and sys.argv[2] == '--production' else
  'http://127.0.0.1:8080/'
  if len(sys.argv) > 2 and sys.argv[2] == '--local' else
  'https://generic-be-test.replit.app/'
)


def main():
  response = requests.get(f'{hostname}setup-project', headers={
    'Authorization': sys.argv[1]
  }).json()
  if response['status'] == 'ko':
    raise Exception(response['error'])

  create_files_and_folders(response['setup'], '.')
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
