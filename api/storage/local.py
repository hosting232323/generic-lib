import os


def upload_file_local(content, filename, folder):
  with open(os.path.join(folder, filename), 'wb') as file:
    file.write(content)


def delete_file_local(filename, folder):
  os.remove(os.path.join(folder, filename))


def list_files_local(folder):
  return [os.path.join(folder, file) for file in os.listdir(folder) if os.path.isfile(os.path.join(folder, file))]
