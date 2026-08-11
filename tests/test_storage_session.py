import io
import os

import pytest

from api.storage import get_full_path
from api.storage.session import SessionWithStorage


class FakeSession:
  """Sessione DB minimale: SessionWithStorage delega qui tutto ciò che non è storage."""

  def __init__(self):
    self.committed = False
    self.rolled_back = False
    self.fail_on_commit = False

  def commit(self):
    if self.fail_on_commit:
      raise RuntimeError('commit fallito')
    self.committed = True

  def rollback(self):
    self.rolled_back = True


@pytest.fixture
def storage(tmp_path, monkeypatch):
  """SessionWithStorage con un DB finto e STATIC_FOLDER su disco temporaneo."""
  fake_session = FakeSession()

  class _Context:
    def __enter__(self):
      return fake_session

    def __exit__(self, *args):
      return False

  monkeypatch.setattr('api.storage.session.Session', lambda: _Context())

  folder = str(tmp_path)
  session = SessionWithStorage()
  session.db = fake_session
  session.folder = folder
  return session


def stored(folder, subfolder='blog'):
  path = os.path.join(folder, 'test', subfolder)
  if not os.path.isdir(path):
    return []
  return sorted(os.listdir(path))


def read_stored(folder, filename, subfolder='blog'):
  with open(os.path.join(folder, 'test', subfolder, filename), 'rb') as file:
    return file.read()


def test_upload_pubblica_il_file_al_commit(storage):
  with storage as session:
    session.upload(io.BytesIO(b'nuovo'), '1.png', session.folder, subfolder='blog')
    assert stored(session.folder) == []  # niente su disco prima del commit
    session.commit()

  assert stored(storage.folder) == ['1.png']
  assert read_stored(storage.folder, '1.png') == b'nuovo'


def test_upload_scartato_se_non_si_committa(storage):
  with storage as session:
    session.upload(io.BytesIO(b'mai-pubblicato'), '1.png', session.folder, subfolder='blog')

  assert stored(storage.folder) == []


def test_upload_scartato_se_il_commit_db_fallisce(storage):
  with storage as session:
    session.db.fail_on_commit = True
    session.upload(io.BytesIO(b'mai-pubblicato'), '1.png', session.folder, subfolder='blog')
    with pytest.raises(RuntimeError):
      session.commit()

  assert stored(storage.folder) == []
  assert storage.db.rolled_back


def test_delete_rimuove_il_file_al_commit(storage):
  with storage as session:
    session.upload(io.BytesIO(b'primo'), '1.png', session.folder, subfolder='blog')
    session.commit()

  with storage as session:
    session.delete_file('1.png', session.folder, subfolder='blog')
    assert stored(session.folder) == ['1.png']  # ancora presente prima del commit
    session.commit()

  assert stored(storage.folder) == []


def test_delete_di_file_inesistente_non_solleva(storage):
  with storage as session:
    session.delete_file('mai-esistito.png', session.folder, subfolder='blog')
    session.commit()

  assert stored(storage.folder) == []


def test_sostituzione_stesso_nome_file_mantiene_il_nuovo_contenuto(storage):
  """Regressione: delete + upload dello stesso path nella stessa transazione.

  È il caso della cover di un post sostituita con un'immagine della stessa
  estensione: il nome file viene riusato perché deriva dall'id del PostFile.
  Se le delete girano dopo gli upload, cancellano il file appena scritto e
  la riga a DB resta a puntare a un path inesistente (404).
  """
  with storage as session:
    session.upload(io.BytesIO(b'vecchia-cover'), '1.jpg', session.folder, subfolder='blog')
    session.commit()

  assert read_stored(storage.folder, '1.jpg') == b'vecchia-cover'

  with storage as session:
    session.delete_file('1.jpg', session.folder, subfolder='blog')
    session.upload(io.BytesIO(b'nuova-cover'), '1.jpg', session.folder, subfolder='blog')
    session.commit()

  assert stored(storage.folder) == ['1.jpg']
  assert read_stored(storage.folder, '1.jpg') == b'nuova-cover'


def test_sostituzione_stesso_nome_file_anche_con_upload_registrato_per_primo(storage):
  """L'esito non deve dipendere dall'ordine in cui il chiamante registra le operazioni."""
  with storage as session:
    session.upload(io.BytesIO(b'vecchia-cover'), '1.jpg', session.folder, subfolder='blog')
    session.commit()

  with storage as session:
    session.upload(io.BytesIO(b'nuova-cover'), '1.jpg', session.folder, subfolder='blog')
    session.delete_file('1.jpg', session.folder, subfolder='blog')
    session.commit()

  assert stored(storage.folder) == ['1.jpg']
  assert read_stored(storage.folder, '1.jpg') == b'nuova-cover'


def test_delete_di_altri_file_convive_con_una_sostituzione(storage):
  """Una delete che non collide deve continuare a cancellare davvero."""
  with storage as session:
    session.upload(io.BytesIO(b'cover'), '1.jpg', session.folder, subfolder='blog')
    session.upload(io.BytesIO(b'galleria'), '2.jpg', session.folder, subfolder='blog')
    session.commit()

  with storage as session:
    session.delete_file('1.jpg', session.folder, subfolder='blog')
    session.upload(io.BytesIO(b'cover-nuova'), '1.jpg', session.folder, subfolder='blog')
    session.delete_file('2.jpg', session.folder, subfolder='blog')
    session.commit()

  assert stored(storage.folder) == ['1.jpg']
  assert read_stored(storage.folder, '1.jpg') == b'cover-nuova'


def test_sostituzione_distingue_le_sottocartelle(storage):
  """Stesso nome file in subfolder diversi: la delete non deve toccare l'altro."""
  with storage as session:
    session.upload(io.BytesIO(b'del-blog'), '1.jpg', session.folder, subfolder='blog')
    session.upload(io.BytesIO(b'dello-shop'), '1.jpg', session.folder, subfolder='shop')
    session.commit()

  with storage as session:
    session.delete_file('1.jpg', session.folder, subfolder='blog')
    session.upload(io.BytesIO(b'blog-nuovo'), '1.jpg', session.folder, subfolder='blog')
    session.commit()

  assert read_stored(storage.folder, '1.jpg', subfolder='blog') == b'blog-nuovo'
  assert read_stored(storage.folder, '1.jpg', subfolder='shop') == b'dello-shop'


def test_niente_file_temporanei_residui(storage, tmp_path):
  import tempfile

  before = set(os.listdir(tempfile.gettempdir()))

  with storage as session:
    session.delete_file('1.jpg', session.folder, subfolder='blog')
    session.upload(io.BytesIO(b'contenuto'), '1.jpg', session.folder, subfolder='blog')
    session.commit()

  after = set(os.listdir(tempfile.gettempdir()))
  assert after - before == set()


@pytest.fixture
def recorded(monkeypatch):
  """Registra le chiamate a upload_file/delete_file senza toccare il disco.

  Serve per le destinazioni remote, che nei test non sono raggiungibili: quello
  che conta e' se la delete viene eseguita o saltata, non il suo effetto.
  """
  calls = {'uploads': [], 'deletes': []}
  monkeypatch.setattr(
    'api.storage.session.upload_file',
    lambda content, **kwargs: calls['uploads'].append((bool(kwargs.get('server')), kwargs['filename'])),
  )
  monkeypatch.setattr(
    'api.storage.session.delete_file',
    lambda **kwargs: calls['deletes'].append((bool(kwargs.get('server')), kwargs['filename'])),
  )
  return calls


def test_upload_locale_non_salta_una_delete_remota_sullo_stesso_path(storage, recorded):
  """Locale e remoto sono destinazioni diverse: la collisione non deve valere fra le due."""
  with storage as session:
    session.upload(io.BytesIO(b'locale'), '1.jpg', session.folder, subfolder='blog')
    session.delete_file('1.jpg', session.folder, subfolder='blog', server=True)
    session.commit()

  assert recorded['deletes'] == [(True, '1.jpg')]
  assert recorded['uploads'] == [(False, '1.jpg')]


def test_upload_remoto_non_salta_una_delete_locale_sullo_stesso_path(storage, recorded):
  with storage as session:
    session.upload(io.BytesIO(b'remoto'), '1.jpg', session.folder, subfolder='blog', server=True)
    session.delete_file('1.jpg', session.folder, subfolder='blog')
    session.commit()

  assert recorded['deletes'] == [(False, '1.jpg')]
  assert recorded['uploads'] == [(True, '1.jpg')]


def test_sostituzione_remota_salta_la_delete_come_quella_locale(storage, recorded):
  """A parita' di destinazione la collisione continua a valere."""
  with storage as session:
    session.upload(io.BytesIO(b'remoto'), '1.jpg', session.folder, subfolder='blog', server=True)
    session.delete_file('1.jpg', session.folder, subfolder='blog', server=True)
    session.commit()

  assert recorded['deletes'] == []
  assert recorded['uploads'] == [(True, '1.jpg')]


def test_get_full_path_coerente_con_il_valore_restituito_da_upload(storage):
  with storage as session:
    returned = session.upload(io.BytesIO(b'x'), '1.jpg', session.folder, subfolder='blog')
    session.commit()

  assert returned == get_full_path(storage.folder, 'blog', None, '1.jpg')
  assert os.path.isfile(returned)
