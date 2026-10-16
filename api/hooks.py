import traceback
from flask import g, request
from werkzeug.exceptions import HTTPException

from .log import write_log
from .telegram import send_telegram_error


EXCLUDED_METHODS = ('OPTIONS', 'HEAD')
EXCLUDED_PATHS = ('/',)
EXCLUDED_PREFIXES = ('/swagger', '/photos')
BODY_EXCLUDED_PREFIXES = ()


def handle_exception(error):
  if isinstance(error, HTTPException):
    return error

  traceback.print_exc()
  g.log_traceback = traceback.format_exc()
  send_telegram_error(g.log_traceback)
  return {'status': 'ko', 'message': 'Errore generico'}, 200


def log_request(
  response,
  log_folder,
  excluded_paths,
  excluded_prefixes,
  user_log_field=None,
  body_excluded_prefixes=BODY_EXCLUDED_PREFIXES,
):
  try:
    if is_loggable(excluded_paths, excluded_prefixes):
      body = extract_response(response)
      if body is not None:
        write_log(
          g.get('log_user'),
          log_folder,
          body,
          swagger=g.get('log_swagger', False),
          user_field=user_log_field,
          with_body=not has_prefix(request.path, body_excluded_prefixes),
        )
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
  if has_prefix(request.path, excluded_prefixes):
    return False
  return True


def has_prefix(path, prefixes):
  """Vero se `path` comincia con uno dei prefissi.

  Il confronto e' sul path grezzo, carattere per carattere: `('/user',)`
  prende anche `/users` e `/user_settings`. Per fermarsi al segmento si passa
  `'/user/'` (e, se serve, anche il path esatto `'/user'`).
  Una stringa sola e' trattata come un prefisso solo: `tuple('/user')`
  varrebbe ('/', 'u', ...) e il '/' prenderebbe tutti i path.
  """
  if not prefixes:
    return False
  if isinstance(prefixes, str):
    prefixes = (prefixes,)
  return path.startswith(tuple(prefixes))


def extract_response(response):
  identified = g.get('log_user') is not None or g.get('log_swagger', False)
  if response.direct_passthrough or not response.is_json:
    if not identified and not g.get('log_traceback'):
      return None
    body = {'content_type': response.content_type, 'status_code': response.status_code}
  else:
    body = response.get_json(silent=True)

  if g.get('log_traceback') and isinstance(body, dict):
    body = {**body, 'traceback': g.log_traceback}
  return body
