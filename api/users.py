import requests
from flask import request
from database_api import Session

from .settings import hostname, default_headers

# Ignore error!
from src.database.schema import User


def register_user_(email: str, password: str = None):
  body = {'email': email}
  if password:
    body['password'] = password
  return requests.post(f'{hostname}register-user', headers=default_headers, json=body).json()


def login_(email: str, password: str):
  return requests.post(f'{hostname}login', headers=default_headers, json={
    'email': email,
    'password': password
  }).json()


def ask_change_password_(email: str):
  return requests.post(f'{hostname}ask-change-password', headers=default_headers, json={
    'email': email
  }).json()


def change_password_(pass_token: str, new_password: str):
  return requests.post(f'{hostname}change-password', headers=default_headers, json={
    'pass_token': pass_token,
    'new_password': new_password
  }).json()


def session_token_decorator_(func):

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
