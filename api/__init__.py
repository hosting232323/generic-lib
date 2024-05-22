from .mail import send_mail_
from .storage import upload_file_, download_file_
from .users import register_user_, login_, change_password_, ask_change_password_, session_token_decorator_


def send_mail(receiver_email: str, body: str, subject: str):
  send_mail_(receiver_email, body, subject)


def upload_file(bucket_name: str, key: str, file_data):
  upload_file_(bucket_name, key, file_data)


def download_file(bucket_name: str, key: str):
  download_file_(bucket_name, key)


def register_user(email: str, password: str = None):
  register_user_(email, password)


def login(email: str, password: str):
  login_(email, password)


def ask_change_password(email: str):
  ask_change_password_(email)


def change_password(pass_token: str, new_password: str):
  change_password_(pass_token, new_password)


def session_token_decorator(func):
  session_token_decorator_(func)
