import threading
import subprocess
from pathlib import Path

from .utils import format_mismatch_message, get_full_path
from ..telegram import send_telegram_message

from .local import _upload_file_local, _delete_file_local, _list_files_local, _folder_backup_local
from .server import _upload_file_server, _delete_file_server, _list_files_server, _folder_backup_server


def upload_file(content, filename, folder, server=None, subfolder=None, ignore_dev=None):
  full_path = get_full_path(folder, subfolder, ignore_dev, filename)
  if not server:
    return _upload_file_local(content, full_path)
  else:
    return _upload_file_server(content, full_path)


def delete_file(filename, folder, server=None, subfolder=None, ignore_dev=None):
  full_path = get_full_path(folder, subfolder, ignore_dev, filename)
  if not server:
    return _delete_file_local(full_path)
  else:
    return _delete_file_server(full_path)


def get_all_filenames(folder, server=None, subfolder=None, ignore_dev=None):
  full_path = get_full_path(folder, subfolder, ignore_dev)
  if not server:
    return _list_files_local(full_path)
  else:
    return _list_files_server(full_path)


def folder_backup(folder_to_backup, server=None):
  def run():
    try:
      if not server:
        _folder_backup_local(folder_to_backup)
      else:
        _folder_backup_server(folder_to_backup)
    except subprocess.CalledProcessError as e:
      send_telegram_message(
        '\n'.join(
          [
            f'*📦 Folder Backup Fallito*\n▶️ `{folder_to_backup}`\n',
            f'*❌ Errore durante il backup ({"server" if server else "local"}):*',
            f'`{e.stderr.strip() or e.stdout.strip() or str(e)}`',
          ]
        )
      )

  thread = threading.Thread(target=run, daemon=True)
  thread.start()


def check_mismatch(db_files, folder, label, subfolder=None):
  files = [Path(path).name for path in _list_files_local(folder, subfolder)]
  send_telegram_message(
    '\n'.join(
      [f'*📊 Report Check Mismatch*\n▶️ {label}\n']
      + format_mismatch_message(
        db_files, files, '\n*❌ File presenti solo nel DB ({}):*', '\n✔️ Nessun file solo nel DB'
      )
      + format_mismatch_message(
        files,
        db_files,
        '\n*❌ File presenti solo in storage local ({}):*',
        '\n✔️ Nessun file solo in storage',
      )
    )
  )
