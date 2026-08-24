from sqlalchemy import create_engine

import database_api


def test_nested_scope_merges_values_and_restores_parent():
  assert database_api.current_scope() == {}

  with database_api.scope(company_id=7):
    assert database_api.current_scope() == {'company_id': 7}
    with database_api.scope(request_id='abc'):
      assert database_api.current_scope() == {'company_id': 7, 'request_id': 'abc'}
    assert database_api.current_scope() == {'company_id': 7}

  assert database_api.current_scope() == {}


def test_scope_values_are_copied_to_new_session(monkeypatch):
  monkeypatch.setattr(database_api, 'engine', create_engine('sqlite:///:memory:'))

  with database_api.scope(company_id=11, request_id='req-1'):
    with database_api.Session() as session:
      assert session.info['company_id'] == 11
      assert session.info['request_id'] == 'req-1'