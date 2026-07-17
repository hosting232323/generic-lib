import os
import threading
import subprocess
from pathlib import Path

from ..settings import IS_DEV
from .utils import format_mismatch_message
from .local import _upload_file_local, _delete_file_local, _list_files_local, _folder_backup_local
from .server import _upload_file_server, _delete_file_server, _list_files_server, _folder_backup_server


_LOCAL_STORAGE_VALUES = (None, False, 'local')
_SERVER_STORAGE_VALUES = (True, 'server')


def upload_file(content, filename, folder, server=None, subfolder=None, ignore_dev=None):
  full_path = get_full_path(folder, subfolder, ignore_dev, filename)
  if _uses_server_storage(server):
    return _upload_file_server(content, full_path)
  return _upload_file_local(content, full_path)


def delete_file(filename, folder, server=None, subfolder=None, ignore_dev=None):
  full_path = get_full_path(folder, subfolder, ignore_dev, filename)
  if _uses_server_storage(server):
    return _delete_file_server(full_path)
  return _delete_file_local(full_path)


def get_all_filenames(folder, server=None, subfolder=None, ignore_dev=None):
  full_path = get_full_path(folder, subfolder, ignore_dev)
  if _uses_server_storage(server):
    return _list_files_server(full_path)
  return _list_files_local(full_path)


def folder_backup(folder_to_backup, server=None):
  server = _uses_server_storage(server)

  def run():
    try:
      if not server:
        _folder_backup_local(folder_to_backup)
      else:
        _folder_backup_server(folder_to_backup)
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
      _send_telegram_message(
        '\n'.join(
          [
            f'**📦 Folder Backup Fallito**\n▶️ `{folder_to_backup}`\n',
            f'**❌ Errore durante il backup ({"server" if server else "local"}):**',
            f'`{_error_details(error)}`',
          ]
        )
      )

  thread = threading.Thread(target=run, daemon=True)
  thread.start()
  return thread


def check_mismatch(db_files, folder, label, subfolder=None, *, recursive=False, ignore_dev=False):
  full_path = get_full_path(folder, subfolder, ignore_dev)
  listed_files = _list_files_local(full_path, recursive=recursive)
  if recursive:
    files = [_normalize_relative_path(Path(path).relative_to(full_path)) for path in listed_files]
    db_files = [_normalize_relative_path(path) for path in db_files]
  else:
    files = [Path(path).name for path in listed_files]

  _send_telegram_message(
    '\n'.join(
      [f'**📊 Report Check Mismatch**\n▶️ {label}\n']
      + format_mismatch_message(
        db_files, files, '\n**❌ File presenti solo nel DB ({}):**', '\n✔️ Nessun file solo nel DB'
      )
      + format_mismatch_message(
        files,
        db_files,
        '\n**❌ File presenti solo in storage local ({}):**',
        '\n✔️ Nessun file solo in storage',
      )
    )
  )


def _normalize_relative_path(path):
  return os.fspath(path).replace('\\', '/').lstrip('/')


def get_full_path(folder, subfolder=None, ignore_dev=False, filename=None):
  root = os.fspath(folder)
  storage_root = root if ignore_dev else os.path.join(root, 'test' if IS_DEV else 'prod')
  full_path = storage_root

  if subfolder:
    subfolder = os.fspath(subfolder)
    if os.path.isabs(subfolder):
      raise ValueError('subfolder deve essere un percorso relativo')
    full_path = os.path.join(full_path, subfolder)

  if filename:
    filename = os.fspath(filename)
    if os.path.basename(filename) != filename:
      raise ValueError('filename non deve contenere cartelle')
    full_path = os.path.join(full_path, filename)

  _validate_path_is_within_root(storage_root, full_path)
  return os.path.normpath(full_path)


def _uses_server_storage(server):
  if isinstance(server, str):
    server = server.strip().lower()

  if server in _LOCAL_STORAGE_VALUES:
    return False
  if server in _SERVER_STORAGE_VALUES:
    return True

  raise ValueError('server deve essere True, False, "server", "local" o None')


def _validate_path_is_within_root(root, full_path):
  absolute_root = os.path.abspath(root)
  absolute_path = os.path.abspath(full_path)
  try:
    is_within_root = os.path.commonpath([absolute_root, absolute_path]) == absolute_root
  except ValueError:
    is_within_root = False

  if not is_within_root:
    raise ValueError('Il percorso storage non puo uscire dalla cartella configurata')


def _send_telegram_message(message):
  from . import send_telegram_message

  return send_telegram_message(message)


def _error_details(error):
  if isinstance(error, subprocess.CalledProcessError):
    return (error.stderr or error.stdout or str(error)).strip()

  return str(error)
