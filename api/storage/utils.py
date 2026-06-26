import os

from ..settings import IS_DEV, RESTIC_PASSWORD, BACKUP_FOLDER, SERVER_NAME


def get_full_path(folder, subfolder, ignore_dev, filename=None):
  if not ignore_dev:
    folder = os.path.join(folder, 'test' if IS_DEV else 'prod')

  if subfolder:
    folder = os.path.join(folder, subfolder)

  return os.path.join(folder, filename) if filename else folder


def format_mismatch_message(first_list: list, second_list: list, success_text: str, failure_text: str):
  mismatch = sorted(set(first_list) - set(second_list))

  if not mismatch:
    return [failure_text]

  mismatch_lines = [f'- {f.replace(chr(92), chr(92) * 2).replace("`", "\\`")}' for f in mismatch]
  return [success_text.format(len(mismatch)), '```'] + mismatch_lines + ['```']


def set_backup_env():
  if not RESTIC_PASSWORD:
    raise ValueError('RESTIC_PASSWORD non configurata')

  if not BACKUP_FOLDER:
    raise ValueError('BACKUP_FOLDER non configurata')

  if not SERVER_NAME:
    raise ValueError('SERVER_NAME non configurato')

  env = os.environ.copy()
  env['RESTIC_PASSWORD'] = RESTIC_PASSWORD
  return env
