import os
import jwt
import pytz
import hashlib
import secrets
from functools import wraps
from datetime import datetime, timedelta
from flask import g, request, jsonify, make_response

from api.settings import IS_DEV
from database_api.operations import create, update, get_by_params
from .setup import DECODE_JWT_TOKEN, ACCESS_TOKEN_MINUTES, REFRESH_TOKEN_DAYS, REFRESH_COOKIE_NAME


REFRESH_COOKIE_PATH = os.environ.get('REFRESH_COOKIE_PATH', '/')
REFRESH_COOKIE_DOMAIN = os.environ.get('REFRESH_COOKIE_DOMAIN') or None
REFRESH_COOKIE_SAMESITE = os.environ.get('REFRESH_COOKIE_SAMESITE', 'Lax')


def _now():
  return datetime.now(pytz.utc)


def _aware(dt):
  # Postgres (timezone=True) rende datetime tz-aware; SQLite li restituisce
  # naive. Normalizziamo a UTC per confronti sicuri su entrambi.
  return dt if dt.tzinfo else dt.replace(tzinfo=pytz.utc)


def _hash_refresh(raw: str) -> str:
  return hashlib.sha256(raw.encode()).hexdigest()


def create_access_token(user_id, role=None) -> str:
  payload = {
    'sub': str(user_id),
    'exp': (_now() + timedelta(minutes=ACCESS_TOKEN_MINUTES)).timestamp(),
  }
  if role is not None:
    payload['role'] = role.value if hasattr(role, 'value') else role
  return jwt.encode(payload, DECODE_JWT_TOKEN, algorithm='HS256')


def _read_access_token():
  auth_header = request.headers.get('Authorization', '')
  token = auth_header[7:] if auth_header.startswith('Bearer ') else auth_header
  return token or None


def build_auth(session_model, get_user_by_id):
  """Costruisce il sistema access/refresh per un progetto.

  - session_model: entita' con user_id, token_hash, expires_at, revoked
  - get_user_by_id: funzione (id) -> user, con attributi id e role
  """

  def _issue_refresh(user_id) -> str:
    raw = secrets.token_urlsafe(48)
    create(
      session_model,
      {
        'user_id': user_id,
        'token_hash': _hash_refresh(raw),
        'expires_at': _now() + timedelta(days=REFRESH_TOKEN_DAYS),
        'revoked': False,
      },
    )
    return raw

  def _find_session(raw: str):
    sessions = get_by_params(session_model, [('token_hash', _hash_refresh(raw))])
    return sessions[0] if sessions else None

  def _set_cookie(response, raw: str):
    response.set_cookie(
      REFRESH_COOKIE_NAME,
      raw,
      max_age=REFRESH_TOKEN_DAYS * 24 * 3600,
      httponly=True,
      secure=not IS_DEV,
      samesite=REFRESH_COOKIE_SAMESITE,
      domain=REFRESH_COOKIE_DOMAIN,
      path=REFRESH_COOKIE_PATH,
    )

  def _token_response(user, raw: str, extra: dict = None):
    body = {'status': 'ok', 'access_token': create_access_token(user.id, getattr(user, 'role', None))}
    if extra:
      body.update(extra)
    response = make_response(jsonify(body))
    _set_cookie(response, raw)
    return response

  def login_response(user, extra: dict = None):
    return _token_response(user, _issue_refresh(user.id), extra)

  def refresh():
    raw = request.cookies.get(REFRESH_COOKIE_NAME)
    if not raw:
      return jsonify({'status': 'session', 'message': 'Sessione assente'}), 401

    session = _find_session(raw)
    if not session or session.revoked or _aware(session.expires_at) < _now():
      return jsonify({'status': 'session', 'message': 'Sessione non valida'}), 401

    user = get_user_by_id(session.user_id)
    if not user:
      update(session, {'revoked': True})
      return jsonify({'status': 'session', 'message': 'Utente non trovato'}), 401

    new_raw = secrets.token_urlsafe(48)
    update(session, {'token_hash': _hash_refresh(new_raw), 'expires_at': _now() + timedelta(days=REFRESH_TOKEN_DAYS)})
    return _token_response(user, new_raw)

  def logout():
    raw = request.cookies.get(REFRESH_COOKIE_NAME)
    if raw:
      session = _find_session(raw)
      if session and not session.revoked:
        update(session, {'revoked': True})

    response = make_response(jsonify({'status': 'ok', 'message': 'Logout effettuato'}))
    response.delete_cookie(REFRESH_COOKIE_NAME, domain=REFRESH_COOKIE_DOMAIN, path=REFRESH_COOKIE_PATH)
    return response

  def authentication(roles=None, allow_query_token=False):
    if callable(roles):
      return _decorate(roles, None, False)
    return lambda func: _decorate(func, roles, allow_query_token)

  def _decorate(func, roles, allow_query_token):
    @wraps(func)
    def wrapper(*args, **kwargs):
      token = request.args.get('token') if allow_query_token else _read_access_token()
      if not token or token == 'null':
        return jsonify({'status': 'session', 'message': 'Token assente'}), 401

      try:
        payload = jwt.decode(token, DECODE_JWT_TOKEN, algorithms=['HS256'])
      except jwt.ExpiredSignatureError:
        return jsonify({'status': 'session', 'message': 'Token scaduto'}), 401
      except jwt.InvalidTokenError:
        return jsonify({'status': 'session', 'message': 'Token non valido'}), 401

      user = get_user_by_id(int(payload['sub']))
      if not user:
        return jsonify({'status': 'session', 'message': 'Utente non trovato'}), 401

      if roles and user.role not in roles:
        return jsonify({'status': 'forbidden', 'message': 'Ruolo non autorizzato'}), 403

      g.log_user = user
      return func(user, *args, **kwargs)

    return wrapper

  return SimpleAuth(login_response, refresh, logout, authentication)


class SimpleAuth:
  def __init__(self, login_response, refresh, logout, authentication):
    self.login_response = login_response
    self.refresh = refresh
    self.logout = logout
    self.authentication = authentication
