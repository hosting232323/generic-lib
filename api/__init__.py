import os
import tempfile
import requests
from flask import request, send_file

# Ignore error!
from database_api import Session
from src.database.schema import User
from src.constants import GENERIC_API_KEY


hostname = 'https://genericbackend.replit.app/'
default_headers = {'Authorization': GENERIC_API_KEY}
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


def send_mail(receiver_email, body, subject):
  return requests.post(f'{hostname}send-mail', headers=default_headers, json={
    'body': body,
    'subject': subject,
    'email': receiver_email
  }).json()


def register_user(email, password=None):
  body = {'email': email}
  if password:
    body['password'] = password
  return requests.post(f'{hostname}register-user', headers=default_headers, json=body).json()


def login(email, password):
  return requests.post(f'{hostname}login', headers=default_headers, json={
    'email': email,
    'password': password
  }).json()


def ask_change_password(email):
    return requests.post(f'{hostname}ask-change-password', headers=default_headers, json={
    'email': email
  }).json()


def change_password(pass_token, new_password):
    return requests.post(f'{hostname}change-password', headers=default_headers, json={
    'pass_token': pass_token,
    'new_password': new_password
  }).json()


def session_token_decorator(func):

  def wrapper(*args, **kwargs):
    if not 'Authorization' in request.headers or request.headers['Authorization'] == 'null':
      return {'status': 'session', 'error': 'Token assente'}

    response = requests.post(f'{hostname}check-token', headers=default_headers, json={
      'token': request.headers['Authorization']
    }).json()
    if response['status'] == 'ko':
      return response

    else:
      return func(get_user_by_mail(response['email']), *args, **kwargs)

  return wrapper


def get_user_by_mail(mail) -> User:
  with Session() as session:
    return session.query(User).filter(
      User.email == mail
    ).first()


def download_file(bucket_name, key):
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


def upload_file(bucket_name, key, file_data):
  return requests.post(
    f'{hostname}upload-file/{bucket_name}/{key}',
    headers=default_headers,
    files={'file': file_data}
  ).json()
