import jwt
import uuid
import pytz
import datetime
from flask import request
from google.oauth2 import id_token
from google.auth.transport import requests

from ..email import send_email
from database_api.operations import create, delete, update
from .setup import get_user_by_email, get_user_by_pass_token, User, DECODE_JWT_TOKEN, GOOGLE_CLIENT_ID


def register_user(email: str, register_email: dict, password: str = None, params: dict = {}):
  if get_user_by_email(email):
    return {'status': 'ko', 'error': 'Email già in uso'}

  params['email'] = email
  if password:
    params['password'] = password
    user = create(User.__subclasses__()[0], params)
    return {
      'status': 'ok',
      'message': 'Utente registrato'
    }

  else:
    params['pass_token'] = str(uuid.uuid4())
    user: User = create(User.__subclasses__()[0], params)
    send_email(
      user.email,
      register_email['body'].format(user.pass_token),
      register_email['subject']
    )
    return {
      'status': 'ok',
      'message': 'Hai ricevuto una mail per verificare il tuo account e proseguire la registrazione'
    }


def delete_user(email: str):
  user = get_user_by_email(email)
  if not user:
    return {'status': 'ko', 'error': 'Utente non trovato'}
  delete(user)
  return {'status': 'ok', 'message': 'Utente eliminato'}


def login(email: str, password: str, session_hours = 2):
  user: User = get_user_by_email(email)
  if not user:
    return {'status': 'ko', 'error': 'Utente non trovato'}

  if user.email != email or user.password != password:
    return {'status': 'ko', 'error': 'Credenziali errate'}

  expiration_time = datetime.datetime.now(pytz.timezone("Europe/Rome")) + datetime.timedelta(hours=session_hours)
  return {
    'status': 'ok',
    'user_id': user.id,
    'token': jwt.encode({
      'email': user.email,
      'exp': expiration_time.astimezone(pytz.utc).timestamp() 
    }, DECODE_JWT_TOKEN, algorithm='HS256')
  }


def ask_change_password(email: str, change_password_email: dict):
  user = get_user_by_email(email)
  if not user:
    return {'status': 'ko', 'error': 'Utente non trovato'}

  user: User = update(user, {'pass_token': str(uuid.uuid4())})

  send_email(
    user.email,
    change_password_email['body'].format(user.pass_token),
    change_password_email['subject']
  )
  return {'status': 'ok', 'message': 'Mail per cambio password inviata'}


def change_password(pass_token: str, new_password: str):
  user = get_user_by_pass_token(pass_token)
  if not user:
    return {'status': 'ko', 'error': 'Questa pagina è scaduta'}

  update(user, {
    'password': new_password,
    'pass_token': None
  })
  return {'status': 'ok', 'message': 'Password aggiornata con successo'}


def google_login(google_token: str, register_email: dict = None, session_hours: int = 2):
    try:
        idinfo = id_token.verify_oauth2_token(
            google_token, 
            requests.Request(),
            GOOGLE_CLIENT_ID
        )

        email = idinfo['email']
        user = get_user_by_email(email)

        if not user:
            if not register_email:
                return {'status': 'ko', 'error': 'User not found and registration is not enabled'}
                
            register_result = register_user(
                email=email,
                register_email=register_email,
                password=None,
                params={'google_user': True}
            )
            if register_result['status'] == 'ko':
                return register_result

            user = get_user_by_email(email)

        expiration_time = datetime.datetime.now(pytz.timezone("Europe/Rome")) + datetime.timedelta(hours=session_hours)
        return {
            'status': 'ok',
            'user_id': user.id,
            'token': jwt.encode({
                'email': user.email,
                'exp': expiration_time.astimezone(pytz.utc).timestamp()
            }, DECODE_JWT_TOKEN, algorithm='HS256')
        }

    except ValueError:
        return {'status': 'ko', 'error': 'Invalid Google token'}


def flask_session_authentication(func):

  def wrapper(*args, **kwargs):
    if not 'Authorization' in request.headers or request.headers['Authorization'] == 'null':
      return {'status': 'session', 'error': 'Token assente'}

    try:
      return func(get_user_by_email(jwt.decode(
        request.headers['Authorization'],
        DECODE_JWT_TOKEN,
        algorithms=['HS256']
      )['email']), *args, **kwargs)
    except jwt.ExpiredSignatureError:
      return {'status': 'session', 'error': 'Token scaduto'}
    except jwt.InvalidTokenError:
      return {'status': 'session', 'error': 'Token non valido'}

  wrapper.__name__ = func.__name__
  return wrapper
