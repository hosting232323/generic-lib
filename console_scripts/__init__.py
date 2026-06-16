import os
import sys
import requests

from database_api.backup import data_export, data_import
from api.storage.client_user import create_client_user, delete_client_user


def db_export():
  data_export(sys.argv[1])


def db_import():
  data_import(sys.argv[1], sys.argv[2])


def setup_storage_client():
  username = sys.argv[1]
  project_name = sys.argv[2]

  print(f'Creazione utente {username} per il progetto {project_name}...')  # noqa: T201
  result = create_client_user(username, project_name)

  key_filename = f'id_ed25519_{username}'
  with open(key_filename, 'w') as f:
    f.write(result['private_key'])
  os.chmod(key_filename, 0o600)

  print(f'\n✅ Utente "{username}" creato su rattata')  # noqa: T201
  print(f'   Cartella: {result["chroot_dir"]}')  # noqa: T201
  print(f'\n📁 Chiave privata salvata in: {key_filename}')  # noqa: T201
  print('\n--- Istruzioni per il cliente ---')  # noqa: T201
  print(f'SFTP interattivo:\n  {result["connection"]["sftp_command"]}')  # noqa: T201
  print(f'\nDownload singolo file:\n  {result["connection"]["scp_example"]}')  # noqa: T201
  print('\nPrerequisiti client: cloudflared installato (https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)')  # noqa: T201


def delete_storage_client():
  """
  Rimuove un utente SFTP da rattata.
  Uso: delete_storage_client <username>
  """
  if len(sys.argv) < 2:
    print('Uso: delete_storage_client <username>')  # noqa: T201
    sys.exit(1)

  username = sys.argv[1]
  delete_client_user(username)
  print(f'✅ Utente "{username}" rimosso da rattata')  # noqa: T201


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
