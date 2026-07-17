import os
import re
from flask import request
from sqlalchemy import text
from sqlalchemy.orm import Session as session_type

from database_api.operations import db_session_decorator
from ..settings import RESTIC_PASSWORD, BACKUP_FOLDER, SERVER_NAME, API_PREFIX


MAX_MISMATCH_LINES = 50

MIME_TYPE_EXTENSIONS = {
  'application/pdf': '.pdf',
  'image/jpeg': '.jpg',
  'image/png': '.png',
  'image/webp': '.webp',
  'video/mp4': '.mp4',
}

_SQL_IDENTIFIER = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


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
def guess_next_id(model, session: session_type = None) -> int:
  table_name = getattr(model, '__tablename__', model)
  if not isinstance(table_name, str) or not _SQL_IDENTIFIER.fullmatch(table_name):
    raise ValueError('model deve essere un nome tabella SQL valido o un model SQLAlchemy')

  return session.execute(text(f"SELECT nextval('{table_name}_id_seq')")).scalar()


def guess_extension(mime_type: str) -> str:
  normalized_mime_type = mime_type.partition(';')[0].strip().lower()
  try:
    return MIME_TYPE_EXTENSIONS[normalized_mime_type]
  except KeyError as error:
    raise ValueError(f'Mime type non supportato: {mime_type}') from error


def get_base_file_path(path):
  components = [request.host_url.rstrip('/')]
  if API_PREFIX:
    components.append(API_PREFIX.strip('/'))
  if path:
    components.append(str(path).strip('/'))

  return '/'.join(components) + '/'
