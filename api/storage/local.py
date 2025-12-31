import os
from ..settings import IS_DEV


def upload_file_local(content, filename, folder, subfolder=None):
  if subfolder:
    key = f'{subfolder}/{filename}'
  else:
    key = get_local_key(filename)
  
  full_path = os.path.join(folder, key)
  os.makedirs(os.path.dirname(full_path), exist_ok=True)

  with open(full_path, 'wb') as file:
    file.write(content)


def delete_file_local(filename, folder):
  os.remove(os.path.join(folder, filename))


def list_files_local(folder):
  return [os.path.join(folder, file) for file in os.listdir(folder) if os.path.isfile(os.path.join(folder, file))]


def get_local_key(key):
  if IS_DEV is None:
    return key
  elif IS_DEV:
    return f'test/{key}'
  else:
    return f'prod/{key}'
