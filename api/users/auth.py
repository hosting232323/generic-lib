import os
import jwt
import pytz
import hashlib
import secrets
from functools import wraps
from datetime import datetime, timedelta
from flask import g, request, jsonify, make_response

from api.settings import IS_DEV
from database_api.operations import create, update, get_by_params, delete_bulk
from .setup import (
  DECODE_JWT_TOKEN,
  ACCESS_TOKEN_MINUTES,
  REFRESH_TOKEN_DAYS,
  REFRESH_COOKIE_NAME,
  REFRESH_TOMBSTONE_DAYS,
)


REFRESH_COOKIE_PATH = os.environ.get('REFRESH_COOKIE_PATH', '/')
REFRESH_COOKIE_DOMAIN = os.environ.get('REFRESH_COOKIE_DOMAIN') or None
REFRESH_COOKIE_SAMESITE = os.environ.get('REFRESH_COOKIE_SAMESITE', 'Lax')
TRANSPORT_HEADER = 'X-Auth-Transport'


def _now():
  return datetime.now(pytz.utc)


def _aware(dt):
  # Postgres (timezone=True) rende datetime tz-aware; SQLite li restituisce
  # naive. Normalizziamo a UTC per confronti sicuri su entrambi.
  return dt if dt.tzinfo else dt.replace(tzinfo=pytz.utc)


def _tombstone_expiry():
  # Una riga revocata resta come lapide: serve solo a riconoscere il replay di
  # un refresh gia' speso, quindi ha una vita molto piu' corta di una sessione.
  return _now() + timedelta(days=REFRESH_TOMBSTONE_DAYS)


def _hash_refresh(raw: str) -> str:
  return hashlib.sha256(raw.encode()).hexdigest()


def _wants_cookie(transport=None) -> bool:
  """Decide dove viaggia il refresh token: cookie HttpOnly o corpo JSON.

  I client browser non dichiarano nulla e prendono il cookie, che e' l'unica
  forma che un XSS non sa leggere. Un client nativo (app mobile, dove SameSite
  non esiste e un cookie jar sarebbe solo un impiccio) chiede esplicitamente il
  trasporto `bearer` con l'header X-Auth-Transport e si tiene il refresh token
  nel proprio storage sicuro.
  """
  choice = transport or request.headers.get(TRANSPORT_HEADER) or 'cookie'
  return str(choice).strip().lower() != 'bearer'


def create_access_token(user_id, role=None) -> str:
  payload = {
    'sub': str(user_id),
    'exp': (_now() + timedelta(minutes=ACCESS_TOKEN_MINUTES)).timestamp(),
  }
  if role is not None:
    payload['role'] = role.value if hasattr(role, 'value') else role
  return jwt.encode(payload, DECODE_JWT_TOKEN, algorithm='HS256')


def _strip_bearer(token):
  # Il prefisso si tollera da qualunque parte arrivi il token: header o query.
  # Chi costruisce l'URL di un media parte spesso dallo stesso valore che
  # metterebbe nell'header, e un `Bearer ` di troppo non e' un buon motivo per
  # rispondere "token non valido".
  if not token:
    return None
  token = token.strip()
  return token[7:].strip() if token.startswith('Bearer ') else token


def _read_access_token():
  return _strip_bearer(request.headers.get('Authorization', '')) or None


def build_auth(session_model, get_user_by_id):
  """Costruisce il sistema access/refresh per un progetto.

  - session_model: entita' con user_id, token_hash, expires_at, revoked
  - get_user_by_id: funzione (id) -> user, con attributi id e role
  """

  def _cleanup_expired_sessions(user_id):
    """Cancella le sessioni scadute dell'utente (lazy cleanup al login).

    Le righe revocate ma non ancora scadute non si toccano: sono le lapidi su
    cui si regge il riconoscimento del replay. Cancellarle renderebbe un token
    rubato indistinguibile da uno inventato.
    """
    old = [s for s in get_by_params(session_model, [('user_id', user_id)]) if _aware(s.expires_at) < _now()]
    if old:
      delete_bulk(old)

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

  def revoke_user_sessions(user_id) -> int:
    """Chiude tutte le sessioni attive di un utente.

    La usano il reuse detection e i progetti quando la password cambia: senza
    questa, reimpostare la password di un utente compromesso non caccia fuori
    chi gli ha rubato il refresh token, che resterebbe valido per giorni.
    """
    active = [s for s in get_by_params(session_model, [('user_id', user_id)]) if not s.revoked]
    for session in active:
      update(session, {'revoked': True, 'expires_at': _tombstone_expiry()})
    return len(active)

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

  def _read_refresh():
    """Legge il refresh token dal trasporto con cui e' arrivato."""
    raw = request.cookies.get(REFRESH_COOKIE_NAME)
    if raw:
      return raw, True
    return (request.get_json(silent=True) or {}).get('refresh_token'), False

  def _token_response(user, raw: str, extra: dict = None, use_cookie: bool = True):
    body = {'status': 'ok', 'access_token': create_access_token(user.id, getattr(user, 'role', None))}
    if extra:
      body.update(extra)
    if not use_cookie:
      body['refresh_token'] = raw

    response = make_response(jsonify(body))
    if use_cookie:
      _set_cookie(response, raw)
    return response

  def login_response(user, extra: dict = None, transport: str = None):
    _cleanup_expired_sessions(user.id)
    return _token_response(user, _issue_refresh(user.id), extra, _wants_cookie(transport))

  def refresh():
    raw, use_cookie = _read_refresh()
    if not raw:
      return jsonify({'status': 'session', 'message': 'Sessione assente'}), 401

    session = _find_session(raw)
    if not session:
      return jsonify({'status': 'session', 'message': 'Sessione non valida'}), 401

    if session.revoked:
      # Reuse detection. Questo refresh e' gia' stato speso (ruotato) o
      # revocato, eppure qualcuno lo ripresenta: o e' una copia rubata, o e' il
      # legittimo proprietario a cui l'hanno rubata e ruotata sotto il naso. Da
      # qui non sappiamo distinguere i due, quindi chiudiamo tutto e
      # costringiamo al login: e' l'unico esito che non lascia dentro il ladro.
      revoke_user_sessions(session.user_id)
      return jsonify({'status': 'session', 'message': 'Sessione non valida'}), 401

    if _aware(session.expires_at) < _now():
      return jsonify({'status': 'session', 'message': 'Sessione non valida'}), 401

    user = get_user_by_id(session.user_id)
    if not user:
      update(session, {'revoked': True, 'expires_at': _tombstone_expiry()})
      return jsonify({'status': 'session', 'message': 'Utente non trovato'}), 401

    # Rotazione: la riga vecchia diventa lapide, il token nuovo nasce sulla sua.
    update(session, {'revoked': True, 'expires_at': _tombstone_expiry()})
    return _token_response(user, _issue_refresh(session.user_id), use_cookie=use_cookie)

  def logout():
    raw, _ = _read_refresh()
    if raw:
      session = _find_session(raw)
      if session and not session.revoked:
        update(session, {'revoked': True, 'expires_at': _tombstone_expiry()})

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
      # L'header resta la via maestra anche sugli endpoint media: la query e'
      # un ripiego per i contesti che non possono mandare header (src di <img>,
      # download diretti). Trattarla come sostituto invece che come aggiunta
      # rendeva impossibile chiamare quegli endpoint via fetch, ed e' cio' che
      # obbliga il frontend a mettere il token nell'URL.
      token = _read_access_token()
      if not token and allow_query_token:
        token = _strip_bearer(request.args.get('token'))
      if not token or token == 'null':
        return jsonify({'status': 'session', 'message': 'Token assente'}), 401

      try:
        payload = jwt.decode(token, DECODE_JWT_TOKEN, algorithms=['HS256'])
      except jwt.ExpiredSignatureError:
        return jsonify({'status': 'session', 'message': 'Token scaduto'}), 401
      except jwt.InvalidTokenError:
        return jsonify({'status': 'session', 'message': 'Token non valido'}), 401

      # Un token firmato ma di formato vecchio (o comunque senza `sub` numerico)
      # non deve diventare un 500: e' solo un token che non vale piu'.
      try:
        user_id = int(payload['sub'])
      except (KeyError, TypeError, ValueError):
        return jsonify({'status': 'session', 'message': 'Token non valido'}), 401

      user = get_user_by_id(user_id)
      if not user:
        return jsonify({'status': 'session', 'message': 'Utente non trovato'}), 401

      if roles and user.role not in roles:
        return jsonify({'status': 'forbidden', 'message': 'Ruolo non autorizzato'}), 403

      g.log_user = user
      return func(user, *args, **kwargs)

    return wrapper

  return SimpleAuth(login_response, refresh, logout, authentication, revoke_user_sessions)


class SimpleAuth:
  def __init__(self, login_response, refresh, logout, authentication, revoke_user_sessions):
    self.login_response = login_response
    self.refresh = refresh
    self.logout = logout
    self.authentication = authentication
    self.revoke_user_sessions = revoke_user_sessions
