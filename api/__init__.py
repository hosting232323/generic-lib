import requests
from flask import request

from .mail import send_mail_
from .settings import hostname, default_headers
from .storage import upload_file_, download_file_, delete_file_
from .users import register_user_, login_, change_password_, ask_change_password_

from database_api import Session
# Ignore error!
from src.database.schema import User


def send_mail(receiver_email: str, body: str, subject: str):
  return send_mail_(receiver_email, body, subject)


def upload_file(bucket_name: str, key: str, file_data):
  return upload_file_(bucket_name, key, file_data)


def download_file(bucket_name: str, key: str):
  return download_file_(bucket_name, key)


def delete_file(bucket_name: str, key: str):
  return delete_file_(bucket_name, key)


def register_user(email: str, password: str = None, register_mail: dict = None):
  return register_user_(email, password, register_mail)


def login(email: str, password: str):
  return login_(email, password)


def ask_change_password(email: str, change_password_mail: dict = None):
  return ask_change_password_(email, change_password_mail)


def change_password(pass_token: str, new_password: str):
  return change_password_(pass_token, new_password)


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


def get_user_by_mail(mail: str) -> User:
  with Session() as session:
    return session.query(User).filter(
      User.email == mail
    ).first()
