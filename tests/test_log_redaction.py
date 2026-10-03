from api.log.serialization import redact


def test_redact_hides_session_tokens_in_a_login_response():
  response = {'status': 'ok', 'access_token': 'aaa.bbb.ccc', 'refresh_token': 'raw-refresh', 'user_id': 7}

  assert redact(response) == {'status': 'ok', 'access_token': '***', 'refresh_token': '***', 'user_id': 7}


def test_redact_hides_session_tokens_in_nested_payloads_and_any_casing():
  payload = {'data': [{'Access_Token': 'aaa', 'refresh_token': 'bbb', 'name': 'x'}]}

  assert redact(payload) == {'data': [{'Access_Token': '***', 'refresh_token': '***', 'name': 'x'}]}
