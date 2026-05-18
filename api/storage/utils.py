import os

from ..settings import IS_DEV, RESTIC_PASSWORD, BACKUP_FOLDER, SERVER_NAME


def get_local_key(key):
  if IS_DEV is None:
    return key
  elif IS_DEV:
    return f'test/{key}'
  else:
    return f'prod/{key}'


def format_mismatch_message(first_list: list, second_list: list, success_text: str, failure_text: str):
  mismatch_lines = list(map(lambda mismatch: f'- {mismatch}', sorted(set(first_list) - set(second_list))))

  return (
    [failure_text]
    if len(mismatch_lines) == 0
    else ([success_text.format(len(mismatch_lines)), '```'] + mismatch_lines + ['```'])
  )


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
