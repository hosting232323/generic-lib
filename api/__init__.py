from .mail import send_mail_
from .storage import upload_file_, download_file_, delete_file_
from .users import register_user_, delete_user_, login_, change_password_, ask_change_password_


def send_mail(receiver_email: str, body: str, subject: str):
  return send_mail_(receiver_email, body, subject)


def upload_file(bucket_name: str, key: str, file_data):
  return upload_file_(bucket_name, key, file_data)


def download_file(bucket_name: str, key: str):
  return download_file_(bucket_name, key)


def delete_file(bucket_name: str, key: str):
  return delete_file_(bucket_name, key)


def register_user(email: str, password: str = None, register_email: dict = None, sender_email: dict = None):
  return register_user_(email, password, register_email, sender_email)


def delete_user(email: str):
  return delete_user_(email)


def login(email: str, password: str):
  return login_(email, password)


def ask_change_password(email: str, change_password_email: dict = None, sender_email: dict = None):
  return ask_change_password_(email, change_password_email, sender_email)


def change_password(pass_token: str, new_password: str):
  return change_password_(pass_token, new_password)
