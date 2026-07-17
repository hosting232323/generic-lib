import io
import os

import pytest

from api.storage import session as storage_session


class FakeSession:
  def __init__(self, commit_error=None):
    self.commit_error = commit_error
    self.committed = False
    self.rolled_back = False

  def commit(self):
    if self.commit_error:
      raise self.commit_error
    self.committed = True

  def rollback(self):
    self.rolled_back = True


class FakeSessionContext:
  def __init__(self, session):
    self.session = session

  def __enter__(self):
    return self.session

  def __exit__(self, exception_type, exception, traceback):
    return False


def _use_fake_session(monkeypatch, commit_error=None):
  session = FakeSession(commit_error=commit_error)
  monkeypatch.setattr(storage_session, 'Session', lambda: FakeSessionContext(session))
  return session


def test_upload_is_deferred_until_commit_then_published(tmp_path, monkeypatch):
  db = _use_fake_session(monkeypatch)
  expected_path = os.path.join(tmp_path, 'test', 'docs', 'file.txt')

  with storage_session.SessionWithStorage() as store:
    path = store.upload(io.BytesIO(b'payload'), 'file.txt', str(tmp_path), subfolder='docs')
    staged_path = store._uploads[0]['staged_path']

    assert path == expected_path
    assert os.path.exists(staged_path)
    assert not os.path.exists(expected_path)

    store.commit()

    assert db.committed
    assert open(expected_path, 'rb').read() == b'payload'
    assert not os.path.exists(staged_path)

  assert os.path.exists(expected_path)


def test_delete_is_deferred_until_commit(tmp_path, monkeypatch):
  _use_fake_session(monkeypatch)
  docs = tmp_path / 'test' / 'docs'
  docs.mkdir(parents=True)
  target = docs / 'old.txt'
  target.write_bytes(b'old')

  with storage_session.SessionWithStorage() as store:
    store.delete_file('old.txt', str(tmp_path), subfolder='docs')
    assert target.exists()

    store.commit()

    assert not target.exists()


def test_commit_failure_rolls_back_and_discards_staged_uploads(tmp_path, monkeypatch):
  db = _use_fake_session(monkeypatch, commit_error=RuntimeError('db down'))
  expected_path = os.path.join(tmp_path, 'test', 'docs', 'file.txt')

  with storage_session.SessionWithStorage() as store:
    store.upload(io.BytesIO(b'payload'), 'file.txt', str(tmp_path), subfolder='docs')
    staged_path = store._uploads[0]['staged_path']

    with pytest.raises(RuntimeError, match='db down'):
      store.commit()

    assert db.rolled_back
    assert not os.path.exists(staged_path)
    assert not os.path.exists(expected_path)


def test_leaving_block_without_commit_discards_staged_uploads(tmp_path, monkeypatch):
  _use_fake_session(monkeypatch)
  expected_path = os.path.join(tmp_path, 'test', 'docs', 'file.txt')

  with storage_session.SessionWithStorage() as store:
    store.upload(io.BytesIO(b'payload'), 'file.txt', str(tmp_path), subfolder='docs')
    staged_path = store._uploads[0]['staged_path']

  assert not os.path.exists(staged_path)
  assert not os.path.exists(expected_path)


def test_upload_rejects_filename_with_path_segments(tmp_path, monkeypatch):
  _use_fake_session(monkeypatch)

  with storage_session.SessionWithStorage() as store:
    with pytest.raises(ValueError, match='filename'):
      store.upload(io.BytesIO(b'payload'), 'nested/file.txt', str(tmp_path), subfolder='docs')
