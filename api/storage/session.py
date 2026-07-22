import os
import shutil
import logging
import tempfile

from database_api import Session
from . import upload_file, delete_file, get_full_path


logger = logging.getLogger(__name__)


class SessionWithStorage:

  def __init__(self):
    self._session_context = None
    self._session = None
    self._uploads: list[dict] = []
    self._deletes: list[dict] = []
    self._committed = False

  def __enter__(self):
    self._uploads = []
    self._deletes = []
    self._committed = False
    self._session_context = Session()
    self._session = self._session_context.__enter__()
    return self

  def __exit__(self, exception_type, exception, traceback):
    try:
      return self._session_context.__exit__(exception_type, exception, traceback)
    finally:
      if not self._committed:
        self._discard_uploads()
      self._session = None
      self._session_context = None

  def __getattr__(self, name):
    if self._session is None:
      raise AttributeError(name)
    return getattr(self._session, name)

  def upload(self, content, filename: str, folder: str, *, server=None, subfolder=None, ignore_dev=None) -> str:
    staged = tempfile.NamedTemporaryFile(delete=False)
    try:
      shutil.copyfileobj(content, staged)
    finally:
      staged.close()

    self._uploads.append(
      {
        'staged_path': staged.name,
        'filename': filename,
        'folder': folder,
        'server': server,
        'subfolder': subfolder,
        'ignore_dev': ignore_dev,
      }
    )
    return get_full_path(folder, subfolder, ignore_dev, filename)

  def delete(self, filename: str, folder: str, *, server=None, subfolder=None, ignore_dev=None):
    self._deletes.append(
      {
        'filename': filename,
        'folder': folder,
        'server': server,
        'subfolder': subfolder,
        'ignore_dev': ignore_dev,
      }
    )

  def commit(self):
    try:
      self._session.commit()
    except Exception:
      self._session.rollback()
      self._discard_uploads()
      raise
    self._committed = True
    self._publish_uploads()
    self._run_deletes()

  def _publish_uploads(self):
    for file_data in self._uploads:
      staged_path = file_data.pop('staged_path')
      try:
        with open(staged_path, 'rb') as content:
          upload_file(content, **file_data)
      except Exception:
        logger.exception('Impossibile pubblicare il file dopo il commit: %s', file_data['filename'])
      finally:
        self._remove_staged(staged_path)
    self._uploads.clear()

  def _run_deletes(self):
    for file_data in self._deletes:
      try:
        delete_file(**file_data)
      except FileNotFoundError:
        pass
      except Exception:
        logger.exception('Impossibile eliminare il file dopo il commit: %s', file_data['filename'])
    self._deletes.clear()

  def _discard_uploads(self):
    for file_data in self._uploads:
      self._remove_staged(file_data['staged_path'])
    self._uploads.clear()
    self._deletes.clear()

  def _remove_staged(self, path):
    try:
      os.remove(path)
    except FileNotFoundError:
      pass
    except Exception:
      logger.exception('Impossibile rimuovere il file temporaneo: %s', path)
