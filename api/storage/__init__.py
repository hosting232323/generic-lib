from .local import upload_file_local, delete_file_local, list_files_local
from .aws import list_files_in_s3, upload_file_to_s3, delete_file_from_s3


def upload_file(content, filename, folder, storage_type):
  if storage_type == 's3':
    upload_file_to_s3(content, filename, folder)
  elif storage_type == 'local':
    upload_file_local(content, filename, folder)


def delete_file(filename, folder, storage_type):
  if storage_type == 's3':
    delete_file_from_s3(filename, folder)
  elif storage_type == 'local':
    delete_file_local(filename, folder)


def get_all_filenames(folder, storage_type):
  if storage_type == 's3':
    return list_files_in_s3(folder)
  elif storage_type == 'local':
    return list_files_local(folder)
