import jwt
import uuid
import pytz
from flask import g, request
from functools import wraps
from google.oauth2 import id_token
from datetime import datetime, timedelta
from google.auth.transport import requests

from ..email import send_email
from database_api.operations import create, delete, update
from .setup import get_user_by_email, get_user_by_pass_token, User, DECODE_JWT_TOKEN, GOOGLE_CLIENT_ID, SESSION_HOURS


def register_user(email: str, register_email: dict, password: str = None, params: dict = {}):
  if get_user_by_email(email):
    return {'status': 'ko', 'message': 'Email già in uso'}

  params['email'] = email
  if password:
    params['password'] = password
    user = create(User.__subclasses__()[0], params)
    return {'status': 'ok', 'message': 'Utente registrato'}

  else:
    params['pass_token'] = str(uuid.uuid4())
    user: User = create(User.__subclasses__()[0], params)
    send_email(
      user.email, register_email['body'].format(domain=request.origin, token=user.pass_token), register_email['subject']
    )
    return {
      'status': 'ok',
      'message': 'Hai ricevuto una mail per verificare il tuo account e proseguire la registrazione',
    }


def delete_user(email: str):
  user = get_user_by_email(email)
  if not user:
    return {'status': 'ko', 'message': 'Utente non trovato'}
  delete(user)
  return {'status': 'ok', 'message': 'Utente eliminato'}


def login(email: str, password: str, get_user=False):
  user = get_user_by_email(email)
  if not user or user.email != email or user.password != password:
    response = {'status': 'ko', 'message': 'Credenziali errate'}
    return (response, None) if get_user else response

  response = {'status': 'ok', 'token': create_jwt_token(user.email)}
  return (response, user) if get_user else response


def ask_change_password(email: str, change_password_email: dict):
  user = get_user_by_email(email)
  if not user:
    return {'status': 'ko', 'message': 'Utente non trovato'}

  user: User = update(user, {'pass_token': str(uuid.uuid4())})

  send_email(
    user.email,
    change_password_email['body'].format(domain=request.origin, token=user.pass_token),
    change_password_email['subject'],
  )
  return {'status': 'ok', 'message': 'Mail per cambio password inviata'}


def change_password(pass_token: str, new_password: str):
  user = get_user_by_pass_token(pass_token)
  if not user:
    return {'status': 'ko', 'message': 'Questa pagina è scaduta'}

  update(user, {'password': new_password, 'pass_token': None})
  return {'status': 'ok', 'message': 'Password aggiornata con successo'}


def google_login(google_token: str, register_email: dict = None, params: dict = None):
  email = id_token.verify_oauth2_token(google_token, requests.Request(), GOOGLE_CLIENT_ID)['email']
  user = get_user_by_email(email)

  if not user:
    if not register_email:
      return {'status': 'ko', 'message': 'User not found and registration is not enabled'}

    register_result = register_user(email=email, register_email=register_email, password=None, params=params)
    if register_result['status'] == 'ko':
      return register_result
    user = get_user_by_email(email)

  return {'status': 'ok', 'user_id': user.id, 'token': create_jwt_token(user.email)}


def create_jwt_token(value: str, token_field: str = 'email'):
  return jwt.encode(
    {
      token_field: value,
      'exp': (datetime.now(pytz.timezone('Europe/Rome')) + timedelta(hours=SESSION_HOURS))
      .astimezone(pytz.utc)
      .timestamp(),
    },
    DECODE_JWT_TOKEN,
    algorithm='HS256',
  )


def build_session_authentication(log_folder, get_user=get_user_by_email, token_field='email', refresh=True):
  def flask_session_authentication(roles=None, allow_query_token=False):
    if callable(roles):
      return _decorate(roles, None, False)
    return lambda func: _decorate(func, roles, allow_query_token)

  def _decorate(func, roles, allow_query_token):
    @wraps(func)
    def wrapper(*args, **kwargs):
      auth_header = request.args.get('token') if allow_query_token else request.headers.get('Authorization')
      if not auth_header or auth_header == 'null':
        return {'status': 'session', 'message': 'Token assente'}

      try:
        user = get_user(jwt.decode(auth_header, DECODE_JWT_TOKEN, algorithms=['HS256'])[token_field])
        if not user:
          return {'status': 'session', 'message': 'Utente non trovato'}

        if roles and user.role not in roles:
          return {'status': 'session', 'message': 'Ruolo non autorizzato'}

        g.log_user = user
        result = func(user, *args, **kwargs)
        if refresh and isinstance(result, dict):
          result['new_token'] = create_jwt_token(getattr(user, token_field), token_field)
        return result

      except jwt.ExpiredSignatureError:
        return {'status': 'session', 'message': 'Token scaduto'}
      except jwt.InvalidTokenError:
        return {'status': 'session', 'message': 'Token non valido'}

    return wrapper

  return flask_session_authentication


def flask_session_authentication(func):
  def wrapper(*args, **kwargs):
    auth_header = request.headers.get('Authorization')
    if not auth_header or auth_header == 'null':
      return {'status': 'session', 'message': 'Token assente'}

    try:
      user = get_user_by_email(jwt.decode(auth_header, DECODE_JWT_TOKEN, algorithms=['HS256'])['email'])
      g.log_user = user
      return func(user, *args, **kwargs)
    except jwt.ExpiredSignatureError:
      return {'status': 'session', 'message': 'Token scaduto'}
    except jwt.InvalidTokenError:
      return {'status': 'session', 'message': 'Token non valido'}

  wrapper.__name__ = func.__name__
  return wrapper


def flask_session_authentication_restore(func):
  def wrapper(*args, **kwargs):
    auth_header = request.headers.get('Authorization')
    if not auth_header or auth_header == 'null':
      return {'status': 'session', 'message': 'Token assente'}

    try:
      user = get_user_by_email(jwt.decode(auth_header, DECODE_JWT_TOKEN, algorithms=['HS256'])['email'])
      if not user:
        return {'status': 'session', 'message': 'Utente non trovato'}

      g.log_user = user
      result = func(user, *args, **kwargs)
      if isinstance(result, dict):
        result['new_token'] = create_jwt_token(user.email)
      return result

    except jwt.ExpiredSignatureError:
      return {'status': 'session', 'message': 'Token scaduto'}
    except jwt.InvalidTokenError:
      return {'status': 'session', 'message': 'Token non valido'}

  wrapper.__name__ = func.__name__
  return wrapper
