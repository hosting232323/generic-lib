"""Test del sistema access/refresh costruito da build_auth.

Il modello mentale: due token con ruoli diversi.

- **access token**: JWT breve, stateless, `sub = user.id`. Autorizza le
  chiamate via header `Authorization: Bearer <token>`. Non e' revocabile ma
  scade in fretta.
- **refresh token**: stringa opaca lunga, in cookie HttpOnly. Non viaggia mai
  nel body ne' nell'header: se ne salva solo l'hash in una riga di `session`.
  Serve solo a ottenere un nuovo access token, ed e' revocabile.

Le regole verificate qui, una per test:

- login: emette access token nel body e setta il cookie refresh HttpOnly;
- refresh: col cookie valido rilascia un nuovo access token e **ruota** il
  refresh (il vecchio smette di valere subito);
- replay: ripresentare un refresh gia' ruotato viene rifiutato con 401;
- logout: revoca la sessione e cancella il cookie;
- decorator: header assente/non valido -> 401; ruolo sbagliato -> 403;
- allow_query_token: legge il token dalla query (per <img>/<video>/download).
"""

from types import SimpleNamespace

import pytest
from flask import Flask

import api.users.auth as auth_module
from api.users.auth import build_auth, create_access_token, REFRESH_COOKIE_NAME


class FakeStore:
  """Rimpiazza le operations del database_api con una lista in memoria."""

  def __init__(self):
    self.rows = []
    self._id = 0

  def create(self, model, params):
    self._id += 1
    row = SimpleNamespace(id=self._id, **params)
    self.rows.append(row)
    return row

  def update(self, instance, params):
    for key, value in params.items():
      setattr(instance, key, value)
    return instance

  def get_by_params(self, model, params_list):
    return [row for row in self.rows if all(getattr(row, key) == value for key, value in params_list)]


USERS = {1: SimpleNamespace(id=1, role='admin')}


@pytest.fixture
def store(monkeypatch):
  fake = FakeStore()
  monkeypatch.setattr(auth_module, 'create', fake.create)
  monkeypatch.setattr(auth_module, 'update', fake.update)
  monkeypatch.setattr(auth_module, 'get_by_params', fake.get_by_params)
  return fake


@pytest.fixture
def auth(store):
  return build_auth(session_model=object, get_user_by_id=lambda uid: USERS.get(int(uid)))


@pytest.fixture
def app(auth):
  app = Flask(__name__)

  @app.route('/login', methods=['POST'])
  def login():
    return auth.login_response(USERS[1])

  @app.route('/refresh', methods=['POST'])
  def refresh():
    return auth.refresh()

  @app.route('/logout', methods=['POST'])
  def logout():
    return auth.logout()

  @app.route('/admin')
  @auth.authentication(roles=['admin'])
  def admin(user):
    return {'status': 'ok', 'who': user.id}

  @app.route('/superadmin')
  @auth.authentication(roles=['superadmin'])
  def superadmin(user):
    return {'status': 'ok'}

  @app.route('/media')
  @auth.authentication(allow_query_token=True)
  def media(user):
    return {'status': 'ok'}

  return app.test_client()


def _refresh_cookie(response):
  for cookie in response.headers.getlist('Set-Cookie'):
    if cookie.startswith(f'{REFRESH_COOKIE_NAME}='):
      return cookie.split(';')[0].split('=', 1)[1]
  return None


def test_login_returns_access_token_and_sets_httponly_cookie(app):
  r = app.post('/login')
  body = r.get_json()
  assert body['status'] == 'ok'
  assert body['access_token']
  set_cookie = next(c for c in r.headers.getlist('Set-Cookie') if c.startswith(REFRESH_COOKIE_NAME))
  assert 'HttpOnly' in set_cookie


def test_refresh_rotates_the_token(app):
  first = _refresh_cookie(app.post('/login'))
  app.set_cookie(REFRESH_COOKIE_NAME, first)
  r = app.post('/refresh')
  assert r.get_json()['access_token']
  second = _refresh_cookie(r)
  assert second and second != first


def test_replay_of_rotated_token_is_rejected(app):
  first = _refresh_cookie(app.post('/login'))
  app.set_cookie(REFRESH_COOKIE_NAME, first)
  app.post('/refresh')
  # Riuso del vecchio refresh (gia' ruotato): non deve piu' valere.
  app.set_cookie(REFRESH_COOKIE_NAME, first)
  r = app.post('/refresh')
  assert r.status_code == 401
  assert r.get_json()['status'] == 'session'


def test_logout_revokes_and_clears_cookie(app):
  cookie = _refresh_cookie(app.post('/login'))
  app.set_cookie(REFRESH_COOKIE_NAME, cookie)
  app.post('/logout')
  app.set_cookie(REFRESH_COOKIE_NAME, cookie)
  r = app.post('/refresh')
  assert r.status_code == 401


def test_missing_access_token_is_401(app):
  r = app.get('/admin')
  assert r.status_code == 401
  assert r.get_json() == {'status': 'session', 'message': 'Token assente'}


def test_valid_access_token_authorizes(app):
  token = create_access_token(1, 'admin')
  r = app.get('/admin', headers={'Authorization': f'Bearer {token}'})
  assert r.get_json()['status'] == 'ok'


def test_wrong_role_is_403(app):
  token = create_access_token(1, 'admin')
  r = app.get('/superadmin', headers={'Authorization': f'Bearer {token}'})
  assert r.status_code == 403
  assert r.get_json()['status'] == 'forbidden'


def test_bearer_prefix_is_optional(app):
  token = create_access_token(1, 'admin')
  r = app.get('/admin', headers={'Authorization': token})
  assert r.get_json()['status'] == 'ok'


def test_query_token_read_when_enabled(app):
  token = create_access_token(1, 'admin')
  assert app.get(f'/media?token={token}').get_json()['status'] == 'ok'
  # Senza query token l'endpoint media resta chiuso.
  assert app.get('/media').status_code == 401
