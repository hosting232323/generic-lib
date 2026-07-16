import os
from flask import request
from sqlalchemy import text
from sqlalchemy.orm import Session as session_type

from database_api.operations import db_session_decorator
from ..settings import RESTIC_PASSWORD, BACKUP_FOLDER, SERVER_NAME, API_PREFIX


MAX_MISMATCH_LINES = 50


def format_mismatch_message(first_list: list, second_list: list, success_text: str, failure_text: str):
  mismatch = sorted(set(first_list) - set(second_list))

  if not mismatch:
    return [failure_text]

  mismatch_lines = [f'- {item}' for item in mismatch[:MAX_MISMATCH_LINES]]
  if len(mismatch) > MAX_MISMATCH_LINES:
    mismatch_lines.append(f'- … e altri {len(mismatch) - MAX_MISMATCH_LINES} file')

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
  return f'{request.scheme}://{request.host}{f"/{API_PREFIX}" if API_PREFIX else ""}/{path}/'
