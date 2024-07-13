import requests

from .settings import hostname, default_headers


def register_user_(email: str, password: str = None, register_mail: dict = None):
  body = {'email': email}
  if password:
    body['password'] = password
  if register_mail:
    body['register_mail'] = register_mail
  return requests.post(
    f'{hostname}register-user',
    headers=default_headers,
    json=body
  ).json()


def login_(email: str, password: str):
  return requests.post(f'{hostname}login', headers=default_headers, json={
    'email': email,
    'password': password
  }).json()


def ask_change_password_(email: str, change_password_mail: dict):
  return requests.post(f'{hostname}ask-change-password', headers=default_headers, json={
    'email': email,
    'change_password_mail': change_password_mail
  }).json()


def change_password_(pass_token: str, new_password: str):
  return requests.post(f'{hostname}change-password', headers=default_headers, json={
    'pass_token': pass_token,
    'new_password': new_password
  }).json()
