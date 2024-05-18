import requests

from .settings import hostname, default_headers


def send_mail_(receiver_email: str, body: str, subject: str):
  return requests.post(f'{hostname}send-mail', headers=default_headers, json={
    'body': body,
    'subject': subject,
    'email': receiver_email
  }).json()
