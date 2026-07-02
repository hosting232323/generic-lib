import jwt
import uuid
import pytz
import traceback
from flask import request
from functools import wraps
from google.oauth2 import id_token
from datetime import datetime, timedelta
from google.auth.transport import requests

from ..log import write_log
from ..email import send_email
from ..settings import SWAGGER_KEY
from ..telegram import send_telegram_error
from database_api.operations import create, delete, update
from .setup import get_user_by_email, get_user_by_pass_token, User, DECODE_JWT_TOKEN, GOOGLE_CLIENT_ID, SESSION_HOURS


def register_user(email: str, register_email: dict, password: str = None, params: dict = {}):
  if get_user_by_email(email):
    return {'status': 'ko', 'error': 'Email già in uso'}

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
    return {'status': 'ko', 'error': 'Utente non trovato'}
  delete(user)
  return {'status': 'ok', 'message': 'Utente eliminato'}


def login(email: str, password: str, get_user=False):
  user = get_user_by_email(email)
  if not user or user.email != email or user.password != password:
    response = {'status': 'ko', 'error': 'Credenziali errate'}
    return (response, None) if get_user else response

  response = {'status': 'ok', 'token': create_jwt_token(user.email)}
  return (response, user) if get_user else response


def ask_change_password(email: str, change_password_email: dict):
  user = get_user_by_email(email)
  if not user:
    return {'status': 'ko', 'error': 'Utente non trovato'}

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
    return {'status': 'ko', 'error': 'Questa pagina è scaduta'}

  update(user, {'password': new_password, 'pass_token': None})
  return {'status': 'ok', 'message': 'Password aggiornata con successo'}


def google_login(google_token: str, register_email: dict = None, params: dict = None):
  email = id_token.verify_oauth2_token(google_token, requests.Request(), GOOGLE_CLIENT_ID)['email']
  user = get_user_by_email(email)

  if not user:
    if not register_email:
      return {'status': 'ko', 'error': 'User not found and registration is not enabled'}

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


def build_session_authentication(
  get_user=get_user_by_email, *, token_field='email', log_folder, swagger=False, refresh=True
):
  def flask_session_authentication(roles=None):
    if callable(roles):
      return _decorate(roles, None)
    return lambda func: _decorate(func, roles)

  def _decorate(func, roles):
    @wraps(func)
    def wrapper(*args, **kwargs):
      if swagger:
        if not SWAGGER_KEY:
          return {'status': 'ko', 'message': 'Errore autenticazione'}
        swagger_key = request.headers.get('SwaggerAuthorization')
        if swagger_key:
          if swagger_key != SWAGGER_KEY:
            return {'status': 'ko', 'message': 'Swagger key non valida'}
          return func(None, *args, **kwargs)

      auth_header = request.headers.get('Authorization')
      if not auth_header or auth_header == 'null':
        return {'status': 'session', 'error': 'Token assente'}

      user = None
      try:
        user = get_user(jwt.decode(auth_header, DECODE_JWT_TOKEN, algorithms=['HS256'])[token_field])
        if not user:
          return {'status': 'session', 'error': 'Utente non trovato'}

        if roles and user.role not in roles:
          return {'status': 'session', 'error': 'Ruolo non autorizzato'}

        result = func(user, *args, **kwargs)
        if refresh and isinstance(result, dict):
          result['new_token'] = create_jwt_token(getattr(user, token_field), token_field)
        write_log(user, log_folder, result)
        return result

      except jwt.ExpiredSignatureError:
        return {'status': 'session', 'error': 'Token scaduto'}
      except jwt.InvalidTokenError:
        return {'status': 'session', 'error': 'Token non valido'}
      except Exception:
        traceback.print_exc()
        tb = traceback.format_exc()
        send_telegram_error(tb)
        if user is not None:
          write_log(user, log_folder, {'status': 'ko', 'error': 'Errore generico', 'traceback': tb})
        return {'status': 'ko', 'error': 'Errore generico'}

    return wrapper

  return flask_session_authentication


def flask_session_authentication(func):
  def wrapper(*args, **kwargs):
    auth_header = request.headers.get('Authorization')
    if not auth_header or auth_header == 'null':
      return {'status': 'session', 'error': 'Token assente'}

    try:
      return func(
        get_user_by_email(jwt.decode(auth_header, DECODE_JWT_TOKEN, algorithms=['HS256'])['email']), *args, **kwargs
      )
    except jwt.ExpiredSignatureError:
      return {'status': 'session', 'error': 'Token scaduto'}
    except jwt.InvalidTokenError:
      return {'status': 'session', 'error': 'Token non valido'}

  wrapper.__name__ = func.__name__
  return wrapper


def flask_session_authentication_restore(func):
  def wrapper(*args, **kwargs):
    auth_header = request.headers.get('Authorization')
    if not auth_header or auth_header == 'null':
      return {'status': 'session', 'error': 'Token assente'}

    try:
      user = get_user_by_email(jwt.decode(auth_header, DECODE_JWT_TOKEN, algorithms=['HS256'])['email'])
      if not user:
        return {'status': 'session', 'error': 'Utente non trovato'}

      result = func(user, *args, **kwargs)
      if isinstance(result, dict):
        result['new_token'] = create_jwt_token(user.email)
      return result

    except jwt.ExpiredSignatureError:
      return {'status': 'session', 'error': 'Token scaduto'}
    except jwt.InvalidTokenError:
      return {'status': 'session', 'error': 'Token non valido'}

  wrapper.__name__ = func.__name__
  return wrapper
