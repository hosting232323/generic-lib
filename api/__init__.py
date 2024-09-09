from .storage import upload_file_, download_file_, delete_file_


def upload_file(bucket_name: str, key: str, file_data):
  return upload_file_(bucket_name, key, file_data)


def download_file(bucket_name: str, key: str):
  return download_file_(bucket_name, key)


def delete_file(bucket_name: str, key: str):
  return delete_file_(bucket_name, key)
