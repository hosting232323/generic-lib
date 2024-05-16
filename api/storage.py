import os
import requests
import tempfile
from flask import send_file

from .settings import hostname, default_headers


mime_types = {
  'png': 'image/png',
  'jpg': 'image/jpeg',
  'jpeg': 'image/jpeg',
  'gif': 'image/gif',
  'pdf': 'application/pdf',
  'txt': 'text/plain',
  'doc': 'application/msword',
  'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
}


def download_file_(bucket_name: str, key: str):
  temp_path = os.path.join(
    tempfile.gettempdir(),
    f'{bucket_name}-{key.replace("_", ".")}'
  )

  with open(temp_path, 'wb') as temp_file:
    temp_file.write(requests.get(
      f'{hostname}download-file/{bucket_name}/{key}',
      headers=default_headers
    ).content)

  return send_file(
    temp_path,
    mimetype=mime_types[key.split('.')[-1]]
  )


def upload_file_(bucket_name: str, key: str, file_data):
  return requests.post(
    f'{hostname}upload-file/{bucket_name}/{key}',
    headers=default_headers,
    files={'file': file_data}
  ).json()
