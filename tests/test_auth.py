"""Test del sistema access/refresh costruito da build_auth.

Il modello mentale: due token con ruoli diversi.

- **access token**: JWT breve, stateless, `sub = user.id`. Autorizza le
  chiamate via header `Authorization: Bearer <token>`. Non e' revocabile ma
  scade in fretta.
- **refresh token**: stringa opaca lunga, di norma in cookie HttpOnly. Se ne
  salva solo l'hash in una riga di `session`. Serve solo a ottenere un nuovo
  access token, ed e' revocabile. Un client nativo, dove il cookie non ha
  senso, puo' chiederlo nel body con l'header X-Auth-Transport: bearer.

Le regole verificate qui, una per test:

- login: emette access token nel body e setta il cookie refresh HttpOnly;
- refresh: col cookie valido rilascia un nuovo access token e **ruota** il
  refresh (il vecchio smette di valere subito);
- replay: ripresentare un refresh gia' ruotato viene rifiutato con 401 **e**
  chiude tutte le sessioni dell'utente (reuse detection);
- logout: revoca la sessione e cancella il cookie;
- decorator: header assente/non valido -> 401; ruolo sbagliato -> 403;
- allow_query_token: legge il token dalla query (per <img>/<video>/download);
- trasporto bearer: login/refresh/logout funzionano senza cookie;
- cleanup al login: butta le sessioni scadute, tiene le lapidi revocate.
"""

import pytz
from datetime import datetime, timedelta
from types import SimpleNamespace

import jwt
import pytest
from flask import Flask

import api.users.auth as auth_module
from api.users.auth import build_auth, create_access_token, REFRESH_COOKIE_NAME
from api.users.setup import DECODE_JWT_TOKEN


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

  def delete_bulk(self, instances):
    for instance in instances:
      self.rows.remove(instance)


USERS = {1: SimpleNamespace(id=1, role='admin')}


@pytest.fixture
def store(monkeypatch):
  fake = FakeStore()
  monkeypatch.setattr(auth_module, 'create', fake.create)
  monkeypatch.setattr(auth_module, 'update', fake.update)
  monkeypatch.setattr(auth_module, 'get_by_params', fake.get_by_params)
  monkeypatch.setattr(auth_module, 'delete_bulk', fake.delete_bulk)
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


def _age_rotations(store):
  """Invecchia le rotazioni oltre la finestra di grazia.

  Entro la grazia un token gia' ruotato che riappare e' due schede aperte;
  fuori, e' un replay. I test sul replay devono quindi guardare al dopo.
  """
  for row in store.rows:
    if getattr(row, 'rotated_at', None):
      row.rotated_at = datetime.now(pytz.utc) - timedelta(hours=1)


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


def test_replay_of_rotated_token_is_rejected(app, store):
  first = _refresh_cookie(app.post('/login'))
  app.set_cookie(REFRESH_COOKIE_NAME, first)
  app.post('/refresh')
  _age_rotations(store)
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


def test_query_token_tolerates_the_bearer_prefix(app):
  # Chi costruisce l'URL di un media parte dallo stesso valore che userebbe
  # nell'header: un `Bearer ` di troppo non deve invalidare il token.
  token = create_access_token(1, 'admin')
  assert app.get(f'/media?token=Bearer {token}').get_json()['status'] == 'ok'


def test_query_token_endpoint_accepts_the_header_too(app):
  # La query e' un ripiego per <img>/download: l'header deve continuare a
  # funzionare, altrimenti quegli endpoint non sono chiamabili via fetch.
  token = create_access_token(1, 'admin')
  assert app.get('/media', headers={'Authorization': f'Bearer {token}'}).get_json()['status'] == 'ok'


def test_token_without_sub_is_401_not_500(app):
  # Un token firmato col nostro segreto ma di formato vecchio (claim `email`
  # invece di `sub`) e' solo un token che non vale piu': non deve diventare un
  # errore 500 con conseguente report d'errore.
  legacy = jwt.encode(
    {'email': 'chi@esempio.it', 'exp': (datetime.now(pytz.utc) + timedelta(hours=1)).timestamp()},
    DECODE_JWT_TOKEN,
    algorithm='HS256',
  )
  r = app.get('/admin', headers={'Authorization': legacy})
  assert r.status_code == 401
  assert r.get_json()['status'] == 'session'


def test_two_tabs_refreshing_together_both_survive(app, store):
  """Il caso normale di due schede aperte non deve sloggiare l'utente.

  Entrambe scoprono l'access token scaduto e chiamano /refresh con lo stesso
  cookie. La seconda arriva con un token gia' ruotato: dentro la finestra di
  grazia e' un doppione innocuo, non un furto.
  """
  first = _refresh_cookie(app.post('/login'))

  app.set_cookie(REFRESH_COOKIE_NAME, first)
  tab_one = app.post('/refresh')
  app.set_cookie(REFRESH_COOKIE_NAME, first)
  tab_two = app.post('/refresh')

  assert tab_one.status_code == 200
  assert tab_two.status_code == 200
  assert _refresh_cookie(tab_one) != _refresh_cookie(tab_two)
  # Ognuna prosegue con la propria sessione, nessuna revoca a tappeto.
  assert len([row for row in store.rows if not row.revoked]) == 2


def test_replay_after_the_grace_window_still_revokes_everything(app, store):
  first = _refresh_cookie(app.post('/login'))
  app.set_cookie(REFRESH_COOKIE_NAME, first)
  app.post('/refresh')

  # La rotazione risale a ben oltre la finestra: ora e' un replay vero.
  _age_rotations(store)

  app.set_cookie(REFRESH_COOKIE_NAME, first)
  assert app.post('/refresh').status_code == 401
  assert all(row.revoked for row in store.rows)


def test_logout_gets_no_grace(app, store):
  # La grazia vale solo per la rotazione: un token revocato dal logout che
  # riappare resta un replay a tutti gli effetti.
  cookie = _refresh_cookie(app.post('/login'))
  app.set_cookie(REFRESH_COOKIE_NAME, cookie)
  app.post('/logout')

  app.set_cookie(REFRESH_COOKIE_NAME, cookie)
  assert app.post('/refresh').status_code == 401
  assert all(row.revoked for row in store.rows)


def test_replay_revokes_every_session_of_the_user(app, store):
  # Due sessioni attive (due dispositivi), poi il replay di un refresh gia'
  # ruotato su uno dei due: non sapendo chi dei due sia il ladro, si chiude
  # tutto e si obbliga al login.
  first = _refresh_cookie(app.post('/login'))
  other = _refresh_cookie(app.post('/login'))
  app.set_cookie(REFRESH_COOKIE_NAME, first)
  app.post('/refresh')
  _age_rotations(store)

  app.set_cookie(REFRESH_COOKIE_NAME, first)
  assert app.post('/refresh').status_code == 401

  app.set_cookie(REFRESH_COOKIE_NAME, other)
  assert app.post('/refresh').status_code == 401
  assert all(row.revoked for row in store.rows)


def test_revoke_user_sessions_closes_the_active_ones(app, auth):
  cookie = _refresh_cookie(app.post('/login'))
  assert auth.revoke_user_sessions(1) == 1

  app.set_cookie(REFRESH_COOKIE_NAME, cookie)
  assert app.post('/refresh').status_code == 401


def test_bearer_transport_returns_refresh_in_body_without_cookie(app):
  # Un client nativo dichiara il trasporto e si prende il refresh token nel
  # body: nessun cookie da gestire, nessun SameSite di mezzo.
  r = app.post('/login', headers={'X-Auth-Transport': 'bearer'})
  body = r.get_json()
  assert body['access_token'] and body['refresh_token']
  assert _refresh_cookie(r) is None


def test_bearer_transport_refreshes_and_rotates_from_body(app, store):
  first = app.post('/login', headers={'X-Auth-Transport': 'bearer'}).get_json()['refresh_token']
  r = app.post('/refresh', json={'refresh_token': first})
  second = r.get_json()['refresh_token']
  assert r.status_code == 200
  assert second and second != first
  # Anche sul canale bearer il token ruotato non vale piu', passata la grazia.
  _age_rotations(store)
  assert app.post('/refresh', json={'refresh_token': first}).status_code == 401


def test_bearer_transport_logout_revokes(app):
  raw = app.post('/login', headers={'X-Auth-Transport': 'bearer'}).get_json()['refresh_token']
  app.post('/logout', json={'refresh_token': raw})
  assert app.post('/refresh', json={'refresh_token': raw}).status_code == 401


def test_login_cleans_up_only_expired_sessions(app, store):
  # Le lapidi revocate ma non scadute vanno tenute: sono cio' che permette di
  # riconoscere un replay. Solo le righe scadute si possono buttare.
  cookie = _refresh_cookie(app.post('/login'))
  app.set_cookie(REFRESH_COOKIE_NAME, cookie)
  app.post('/refresh')
  tombstones = [row for row in store.rows if row.revoked]
  assert tombstones

  app.post('/login')
  assert [row for row in store.rows if row.revoked] == tombstones

  tombstones[0].expires_at = datetime.now(pytz.utc) - timedelta(days=1)
  app.post('/login')
  assert tombstones[0] not in store.rows
