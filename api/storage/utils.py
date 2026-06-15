import os
from flask import request
from sqlalchemy import text
from sqlalchemy.orm import Session as session_type

from database_api.operations import db_session_decorator
from ..settings import IS_DEV, RESTIC_PASSWORD, BACKUP_FOLDER, SERVER_NAME, API_PREFIX


def get_full_path(folder, subfolder, ignore_dev, filename=None):
  if not ignore_dev:
    folder = os.path.join(folder, 'test' if IS_DEV else 'prod')

  if subfolder:
    folder = os.path.join(folder, subfolder)

  return os.path.join(folder, filename) if filename else folder


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


@db_session_decorator(commit=True)
def guess_next_id(model: str, session: session_type = None) -> int:
  return session.execute(text(f"SELECT nextval('{model}_id_seq')")).scalar()


def guess_extension(mime_type: str) -> str:
  if mime_type == 'image/jpeg':
    return '.jpg'
  if mime_type == 'image/png':
    return '.png'
  if mime_type == 'image/webp':
    return '.webp'
  if mime_type == 'video/mp4':
    return '.mp4'
  if mime_type == 'application/pdf':
    return '.pdf'

  raise ValueError('Mime type non supportato')


def get_base_file_path(path):
  return f'http{"s" if not IS_DEV else ""}://{request.host}{f"/{API_PREFIX}" if API_PREFIX else ""}/{path}/'
