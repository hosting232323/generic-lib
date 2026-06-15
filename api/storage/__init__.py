import threading
import subprocess
from pathlib import Path

from .utils import format_mismatch_message
from ..telegram import send_telegram_message

from .local import upload_file_local, delete_file_local, list_files_local, folder_backup_local
from .server import list_files_server, delete_file_server, upload_file_server, folder_backup_server


def upload_file(content, filename, folder, server=None, subfolder=None, ignore_dev=None):
  if not server:
    return upload_file_local(content, filename, folder, subfolder, ignore_dev)
  else:
    return upload_file_server(content, filename, folder, subfolder, ignore_dev)


def delete_file(filename, folder, server=None, subfolder=None, ignore_dev=None):
  if not server:
    delete_file_local(filename, folder, subfolder, ignore_dev)
  else:
    return delete_file_server(filename, folder, subfolder, ignore_dev)


def get_all_filenames(folder, server=None, subfolder=None, ignore_dev=None):
  if not server:
    return list_files_local(folder, subfolder, ignore_dev)
  else:
    return list_files_server(folder, subfolder, ignore_dev)


def folder_backup(folder_to_backup, server=None):
  def run():
    try:
      if not server:
        folder_backup_local(folder_to_backup)
      else:
        folder_backup_server(folder_to_backup)
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
  files = [Path(path).name for path in list_files_local(folder, subfolder)]
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
