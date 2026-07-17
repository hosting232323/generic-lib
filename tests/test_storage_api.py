import io
import os
from types import SimpleNamespace

import pytest
from flask import Flask

import api.storage as storage
from api.storage import server as server_backend
from api.storage import service
from api.storage import utils as storage_utils


PUBLIC_STORAGE_API = {
  'check_mismatch',
  'delete_file',
  'folder_backup',
  'get_all_filenames',
  'get_base_file_path',
  'get_full_path',
  'guess_extension',
  'guess_next_id',
  'upload_file',
}


def test_public_api_contains_only_consumer_facing_symbols():
  assert set(storage.__all__) == PUBLIC_STORAGE_API
  assert all(callable(getattr(storage, name)) for name in storage.__all__)


def test_storage_selector_accepts_explicit_names(monkeypatch):
  calls = []
  monkeypatch.setattr(service, '_upload_file_local', lambda content, path: calls.append(('local', path)) or path)
  monkeypatch.setattr(service, '_upload_file_server', lambda content, path: calls.append(('server', path)) or path)

  storage.upload_file(io.BytesIO(b'local'), 'local.txt', 'files', server='local')
  storage.upload_file(io.BytesIO(b'server'), 'server.txt', 'files', server='server')

  assert [backend for backend, _ in calls] == ['local', 'server']

  with pytest.raises(ValueError, match='server deve essere'):
    storage.upload_file(io.BytesIO(), 'invalid.txt', 'files', server='invalid')


def test_get_full_path_keeps_paths_inside_environment_root(tmp_path, monkeypatch):
  monkeypatch.setattr(service, 'IS_DEV', True)

  assert storage.get_full_path(tmp_path, 'images/blog', filename='cover.jpg') == os.path.join(
    tmp_path, 'test', 'images', 'blog', 'cover.jpg'
  )

  with pytest.raises(ValueError, match='uscire'):
    storage.get_full_path(tmp_path, '..')
  with pytest.raises(ValueError, match='filename'):
    storage.get_full_path(tmp_path, filename='../secret.txt')
  with pytest.raises(ValueError, match='relativo'):
    storage.get_full_path(tmp_path, tmp_path.parent)


def test_local_upload_is_streamed_and_atomic(tmp_path, monkeypatch):
  monkeypatch.setattr(service, 'IS_DEV', True)

  class ChunkedContent(io.BytesIO):
    def __init__(self, value):
      super().__init__(value)
      self.read_sizes = []

    def read(self, size=-1):
      self.read_sizes.append(size)
      return super().read(size)

  content = ChunkedContent(b'a' * (1024 * 1024 + 5))
  path = storage.upload_file(content, 'payload.bin', tmp_path, subfolder='documents')

  assert path == os.path.join(tmp_path, 'test', 'documents', 'payload.bin')
  assert open(path, 'rb').read() == b'a' * (1024 * 1024 + 5)
  assert content.read_sizes and all(size == 1024 * 1024 for size in content.read_sizes)
  assert not list((tmp_path / 'test' / 'documents').glob('.generic-lib-upload-*'))


def test_listing_is_sorted_and_missing_folder_is_empty(tmp_path, monkeypatch):
  monkeypatch.setattr(service, 'IS_DEV', True)
  folder = tmp_path / 'test' / 'photos'
  folder.mkdir(parents=True)
  (folder / 'b.jpg').write_bytes(b'b')
  (folder / 'a.jpg').write_bytes(b'a')
  (folder / 'nested').mkdir()

  assert [os.path.basename(path) for path in storage.get_all_filenames(tmp_path, subfolder='photos')] == [
    'a.jpg',
    'b.jpg',
  ]
  assert storage.get_all_filenames(tmp_path, subfolder='missing') == []


def test_folder_backup_normalizes_local_string_and_returns_thread(monkeypatch):
  calls = []
  monkeypatch.setattr(service, '_folder_backup_local', lambda folder: calls.append(folder))

  thread = storage.folder_backup('/data/files', server='local')
  thread.join(timeout=2)

  assert calls == ['/data/files']
  assert not thread.is_alive()


def test_remote_commands_quote_storage_paths(monkeypatch):
  commands = []

  def fake_run(command, **kwargs):
    commands.append(command)
    return SimpleNamespace(stdout='')

  monkeypatch.setattr(server_backend, 'BACKUP_SSH_CONFIG', 'backup')
  monkeypatch.setattr(server_backend.subprocess, 'run', fake_run)

  dangerous_path = '/srv/files/name; touch hacked'
  server_backend._delete_file_server(dangerous_path)
  assert commands[-1][2] == "rm -- '/srv/files/name; touch hacked'"

  assert server_backend._list_files_server(dangerous_path) == []
  assert "'/srv/files/name; touch hacked'" in commands[-1][2]


def test_public_helpers_are_normalized_and_validate_identifiers(monkeypatch):
  assert storage.guess_extension('Image/JPEG; charset=binary') == '.jpg'

  executed = []
  session = SimpleNamespace(execute=lambda query: executed.append(str(query)) or SimpleNamespace(scalar=lambda: 7))

  class Photo:
    __tablename__ = 'photo'

  assert storage.guess_next_id(Photo, session=session) == 7
  assert executed == ["SELECT nextval('photo_id_seq')"]

  with pytest.raises(ValueError, match='nome tabella SQL valido'):
    storage.guess_next_id('photo; DROP TABLE photo', session=session)

  app = Flask(__name__)
  monkeypatch.setattr(storage_utils, 'API_PREFIX', '/api/')
  with app.test_request_context(base_url='https://example.test/'):
    assert storage.get_base_file_path('/photos/blog/') == 'https://example.test/api/photos/blog/'
