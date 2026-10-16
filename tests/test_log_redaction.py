import json

from flask import Flask, request

from api import register_flask_hooks
from api.log.paths import get_log_dir
from api.hooks import has_prefix
from api.log.serialization import redact
from api.secret_keys import normalize_key


def test_redact_hides_session_tokens_in_a_login_response():
  response = {'status': 'ok', 'access_token': 'aaa.bbb.ccc', 'refresh_token': 'raw-refresh', 'user_id': 7}

  assert redact(response) == {'status': 'ok', 'access_token': '***', 'refresh_token': '***', 'user_id': 7}


def test_redact_hides_session_tokens_in_nested_payloads_and_any_casing():
  payload = {'data': [{'Access_Token': 'aaa', 'refresh_token': 'bbb', 'name': 'x'}]}

  assert redact(payload) == {'data': [{'Access_Token': '***', 'refresh_token': '***', 'name': 'x'}]}


def test_redact_hides_any_field_that_looks_like_a_password_or_a_secret():
  payload = {
    'admin_password': 'p1',
    'confirm-password': 'p2',
    'currentPassword': 'p3',
    'webhook_secret': 's1',
    'api_key': 'k1',
    'device_token': 't1',
    'nickname': 'mario',
    'token_count': 3,
  }

  assert redact(payload) == {
    'admin_password': '***',
    'confirm-password': '***',
    'currentPassword': '***',
    'webhook_secret': '***',
    'api_key': '***',
    'device_token': '***',
    'nickname': 'mario',
    'token_count': 3,
  }


def test_redact_hides_camel_case_secrets_sent_by_the_frontend():
  payload = {
    'accessToken': 'a',
    'refreshToken': 'r',
    'apiKey': 'k',
    'idToken': 'i',
    'APIKey': 'k2',
    'X-Auth-Token': 'x',
    'userId': 7,
    'tokenCount': 2,
  }

  assert redact(payload) == {
    'accessToken': '***',
    'refreshToken': '***',
    'apiKey': '***',
    'idToken': '***',
    'APIKey': '***',
    'X-Auth-Token': '***',
    'userId': 7,
    'tokenCount': 2,
  }


def test_normalize_key_turns_camel_case_and_dashes_into_snake_case():
  assert normalize_key('accessToken') == 'access_token'
  assert normalize_key('Access-Token') == 'access_token'
  assert normalize_key('APIKey') == 'api_key'
  assert normalize_key('ACCESS_TOKEN') == 'access_token'


def test_redact_hides_password_metadata_on_purpose():
  # Falsi positivi voluti (vedi api/secret_keys.py): meglio nascondere un flag
  # che lasciare in chiaro una password con un nome nuovo.
  assert redact({'has_password': True, 'password_changed_at': '2026-10-16'}) == {
    'has_password': '***',
    'password_changed_at': '***',
  }


def test_has_prefix_treats_a_single_string_as_one_prefix():
  assert has_prefix('/user/login', '/user')
  assert not has_prefix('/company', '/user')
  assert has_prefix('/users', ('/user',))
  assert not has_prefix('/users', ('/user/',))
  assert not has_prefix('/user/login', ())
  assert not has_prefix('/user/login', None)


def _read_log_lines(log_folder):
  files = list(get_log_dir(log_folder).glob('*/*.jsonl'))
  return [json.loads(line) for file in files for line in file.read_text(encoding='utf-8').splitlines()]


def _app(log_folder, **kwargs):
  app = Flask(__name__)
  register_flask_hooks(app, log_folder, **kwargs)

  @app.route('/user/login', methods=['POST'])
  def login():
    return {'status': 'ok', 'access_token': 'aaa.bbb.ccc', 'user_id': 7}

  @app.route('/company', methods=['POST'])
  def company():
    return {'status': 'ok', 'company': {'name': request.json['name']}}

  return app


def test_the_log_line_never_carries_headers_cookies_or_query_tokens(tmp_path):
  app = _app(str(tmp_path))

  app.test_client().post(
    '/company?token=query-secret',
    json={'name': 'Acme', 'admin_password': 'body-secret'},
    headers={'Authorization': 'Bearer header-secret', 'Cookie': 'refresh_token=cookie-secret'},
  )

  [entry] = _read_log_lines(str(tmp_path))
  dumped = json.dumps(entry)
  for secret in ('query-secret', 'body-secret', 'header-secret', 'cookie-secret'):
    assert secret not in dumped
  assert entry['request']['json']['name'] == 'Acme'
  assert entry['response'] == {'status': 'ok', 'company': {'name': 'Acme'}}


def test_body_excluded_prefixes_keep_only_method_path_and_outcome(tmp_path):
  app = _app(str(tmp_path), body_excluded_prefixes=('/user',))

  app.test_client().post('/user/login', json={'email': 'mario', 'password': 'segreta'})
  app.test_client().post('/company', json={'name': 'Acme'})

  company_entry, login_entry = sorted(_read_log_lines(str(tmp_path)), key=lambda entry: entry['request']['path'])
  assert company_entry['request']['path'] == '/company'
  assert company_entry['request']['json'] == {'name': 'Acme'}
  assert login_entry['request'] == {'method': 'POST', 'path': '/user/login'}
  assert login_entry['response'] == {'status': 'ok'}
