import threading
import subprocess
from pathlib import Path

from .utils import format_mismatch_message
from ..telegram import send_telegram_message

from .aws import list_files_in_s3, upload_file_to_s3, delete_file_from_s3
from .local import (
  upload_file_local,
  delete_file_local,
  list_files_local,
  folder_backup_local,
  cleanup_folder_backups_local,
)
from .server import (
  list_files_server,
  delete_file_server,
  upload_file_server,
  folder_backup_server,
  cleanup_folder_backups_server,
)


def upload_file(content, filename, folder, storage_type, subfolder=None, ignore_dev=None):
  if storage_type == 's3':
    return upload_file_to_s3(content, filename, folder, subfolder)
  elif storage_type == 'local':
    return upload_file_local(content, filename, folder, subfolder, ignore_dev)
  elif storage_type == 'server':
    return upload_file_server(content, filename, folder, subfolder, ignore_dev)


def delete_file(filename, folder, storage_type, subfolder=None, ignore_dev=None):
  if storage_type == 's3':
    delete_file_from_s3(filename, folder, subfolder)
  elif storage_type == 'local':
    delete_file_local(filename, folder, subfolder, ignore_dev)
  elif storage_type == 'server':
    return delete_file_server(filename, folder, subfolder, ignore_dev)


def get_all_filenames(folder, storage_type, subfolder=None, ignore_dev=None):
  if storage_type == 's3':
    return list_files_in_s3(folder, subfolder)
  elif storage_type == 'local':
    return list_files_local(folder, subfolder, ignore_dev)
  elif storage_type == 'server':
    return list_files_server(folder, subfolder, ignore_dev)


def folder_backup(folder_to_backup, storage_type):
  def run():
    try:
      if storage_type == 'local':
        folder_backup_local(folder_to_backup)
        cleanup_folder_backups_local()
      elif storage_type == 'server':
        folder_backup_server(folder_to_backup)
        cleanup_folder_backups_server()
    except subprocess.CalledProcessError as e:
      send_telegram_message(
        '\n'.join(
          [
            f'*📦 Folder Backup Fallito*\n▶️ `{folder_to_backup}`\n',
            f'*❌ Errore durante il backup ({storage_type}):*',
            f'`{e.stderr.strip() or e.stdout.strip() or str(e)}`',
          ]
        )
      )

  thread = threading.Thread(target=run, daemon=True)
  thread.start()


def check_mismatch(db_files, folder, label, storage_type, subfolder=None):
  if storage_type == 's3':
    files = [path for path in list_files_in_s3(folder, subfolder) if not path.endswith('/')]
  elif storage_type == 'local':
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
        '\n*❌ File presenti solo in storage ' + storage_type + ' ({}):*',
        '\n✔️ Nessun file solo in storage',
      )
    )
  )
