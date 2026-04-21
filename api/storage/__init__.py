from pathlib import Path

from ..telegram import send_telegram_message
from .local import upload_file_local, delete_file_local, list_files_local
from .aws import list_files_in_s3, upload_file_to_s3, delete_file_from_s3


def upload_file(content, filename, folder, storage_type, subfolder=None):
  if storage_type == 's3':
    return upload_file_to_s3(content, filename, folder, subfolder)
  elif storage_type == 'local':
    return upload_file_local(content, filename, folder, subfolder)


def delete_file(filename, folder, storage_type, subfolder=None):
  if storage_type == 's3':
    delete_file_from_s3(filename, folder, subfolder)
  elif storage_type == 'local':
    delete_file_local(filename, folder, subfolder)


def get_all_filenames(folder, storage_type, subfolder=None):
  if storage_type == 's3':
    return list_files_in_s3(folder, subfolder)
  elif storage_type == 'local':
    return list_files_local(folder, subfolder)


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


def format_mismatch_message(first_list: list, second_list: list, success_text: str, failure_text: str):
  mismatch_lines = list(map(lambda mismatch: f'- {mismatch}', sorted(set(first_list) - set(second_list))))

  return (
    [failure_text]
    if len(mismatch_lines) == 0
    else ([success_text.format(len(mismatch_lines)), '```'] + mismatch_lines + ['```'])
  )
