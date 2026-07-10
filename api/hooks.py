import traceback
from flask import g, request
from werkzeug.exceptions import HTTPException

from .log import write_log
from .telegram import send_telegram_error


EXCLUDED_METHODS = ('OPTIONS', 'HEAD')
EXCLUDED_PATHS = ('/',)
EXCLUDED_PREFIXES = ('/swagger', '/photos')


def handle_exception(error):
  if isinstance(error, HTTPException):
    return error

  traceback.print_exc()
  g.log_traceback = traceback.format_exc()
  send_telegram_error(g.log_traceback)
  return {'status': 'ko', 'message': 'Errore generico'}, 200


def log_request(response, log_folder, excluded_paths, excluded_prefixes, user_log_fields=None):
  try:
    if is_loggable(excluded_paths, excluded_prefixes):
      body = extract_response(response)
      if body is not None:
        write_log(g.get('log_user'), log_folder, body, swagger=g.get('log_swagger', False), user_fields=user_log_fields)
  except Exception:
    traceback.print_exc()
  return response


def is_loggable(excluded_paths, excluded_prefixes):
  if request.method in EXCLUDED_METHODS:
    return False
  if request.endpoint == 'static':
    return False
  if request.path in excluded_paths:
    return False
  if excluded_prefixes and request.path.startswith(tuple(excluded_prefixes)):
    return False
  return True


def extract_response(response):
  identified = g.get('log_user') is not None or g.get('log_swagger', False)

  # risposte streaming/file (send_file, generatori) o non JSON: il body non va letto,
  # si logga un sommario e solo per richieste identificate (evita rumore da scanner/404)
  if response.direct_passthrough or not response.is_json:
    if not identified and not g.get('log_traceback'):
      return None
    body = {'content_type': response.content_type, 'status_code': response.status_code}
  else:
    body = response.get_json(silent=True)

  if g.get('log_traceback') and isinstance(body, dict):
    body = {**body, 'traceback': g.log_traceback}
  return body
