"""Test del decorator di sessione costruito da build_session_authentication.

Di default il decorator legge il token JWT dall'header Authorization. Alcune
richieste pero' quell'header non possono proprio inviarlo: sono quelle
generate dal browser per un <img>, un <video> o un link di download, dove
l'URL e' l'unico canale disponibile. Per questi casi c'e' `token_from_query`,
che fa leggere il token dalla query string (`?token=...`).

L'opzione **sostituisce** la sorgente, non la affianca: un endpoint dichiara
da dove arriva il suo token, e legge solo da li'. La scelta e' voluta — un
endpoint nato per un <img> ha un unico canale possibile, e due canali
significherebbero due percorsi da ragionare e una regola di precedenza da
ricordare. Da qui il nome: non "consenti anche", ma "il token arriva dalla
query".

Il rovescio della medaglia, da tenere presente quando si abilita: un token in
query string finisce nei log d'accesso del server, mentre un header no. Va
quindi dichiarata solo dove il tipo di richiesta la impone.

Le regole che ne derivano, una per test:

- endpoint di default: legge l'header, e ignora la query anche se valida;
- endpoint con token_from_query: legge la query, e ignora l'header anche se
  valido (nemmeno come ripiego);
- l'uso "nudo" (@session_auth senza parentesi) resta sull'header;
- il nome del parametro e' configurabile alla costruzione (query_token_param);
- ruoli, refresh del token e messaggi d'errore restano quelli di sempre.
"""

from types import SimpleNamespace

import pytest
from flask import Flask

from api.users import build_session_authentication, create_jwt_token


USERS = {
  'user@example.com': SimpleNamespace(email='user@example.com', role='admin'),
}


def fake_get_user(email):
  return USERS.get(email)


def build_app(**auth_kwargs):
  session_auth = build_session_authentication(log_folder='/tmp', get_user=fake_get_user, **auth_kwargs)
  app = Flask(__name__)

  @app.route('/bare')
  @session_auth
  def bare(user):
    return {'status': 'ok', 'who': user.email}

  @app.route('/query-on')
  @session_auth(token_from_query=True)
  def query_on(user):
    return {'status': 'ok', 'who': user.email}

  @app.route('/query-on-admin')
  @session_auth(roles=['admin'], token_from_query=True)
  def query_on_admin(user):
    return {'status': 'ok', 'who': user.email}

  @app.route('/query-on-superadmin')
  @session_auth(roles=['superadmin'], token_from_query=True)
  def query_on_superadmin(user):
    return {'status': 'ok', 'who': user.email}

  return app.test_client()


@pytest.fixture
def token():
  return create_jwt_token('user@example.com')


@pytest.fixture
def client():
  return build_app()


def test_header_token_still_works(client, token):
  r = client.get('/bare', headers={'Authorization': token})
  assert r.get_json()['status'] == 'ok'


def test_missing_token_is_rejected(client):
  assert client.get('/bare').get_json() == {'status': 'session', 'message': 'Token assente'}


def test_query_token_ignored_by_default(client, token):
  # L'endpoint /bare non abilita la query: il token li' non deve valere.
  assert client.get(f'/bare?token={token}').get_json() == {'status': 'session', 'message': 'Token assente'}


def test_query_token_accepted_when_enabled(client, token):
  body = client.get(f'/query-on?token={token}').get_json()
  assert body['status'] == 'ok'
  assert body['who'] == 'user@example.com'


def test_header_ignored_when_token_comes_from_query(client, token):
  # Sorgente esclusiva: su un endpoint con token_from_query un header valido,
  # da solo, non autentica — il token deve stare nella query.
  r = client.get('/query-on', headers={'Authorization': token})
  assert r.get_json() == {'status': 'session', 'message': 'Token assente'}


def test_query_wins_when_both_are_sent(client, token):
  # Stessa regola con entrambi presenti: conta solo la query, e qui porta un
  # utente inesistente nonostante l'header sia buono.
  bad = create_jwt_token('nobody@example.com')
  r = client.get(f'/query-on?token={bad}', headers={'Authorization': token})
  assert r.get_json() == {'status': 'session', 'message': 'Utente non trovato'}


def test_query_token_null_string_is_rejected(client):
  assert client.get('/query-on?token=null').get_json() == {'status': 'session', 'message': 'Token assente'}


def test_query_token_invalid_is_rejected(client):
  assert client.get('/query-on?token=not-a-jwt').get_json() == {'status': 'session', 'message': 'Token non valido'}


def test_roles_enforced_with_query_token(client, token):
  # Utente 'admin': ammesso su roles=['admin'], negato su roles=['superadmin'].
  assert client.get(f'/query-on-admin?token={token}').get_json()['status'] == 'ok'
  assert client.get(f'/query-on-superadmin?token={token}').get_json() == {
    'status': 'session',
    'message': 'Ruolo non autorizzato',
  }


def test_custom_query_param_name(token):
  client = build_app(query_token_param='access_token')
  assert client.get(f'/query-on?access_token={token}').get_json()['status'] == 'ok'
  # Il nome vecchio non e' piu' riconosciuto.
  assert client.get(f'/query-on?token={token}').get_json() == {'status': 'session', 'message': 'Token assente'}


def test_query_token_result_is_refreshed(client, token):
  r = client.get(f'/query-on?token={token}')
  assert 'new_token' in r.get_json()
