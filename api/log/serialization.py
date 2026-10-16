import json
import decimal
import re

from .paths import LOG_MAX_FIELD_CHARS, LOG_MAX_LINE_BYTES


REDACTED_KEYS = {
  'password',
  'new_password',
  'old_password',
  'pass_token',
  'token',
  'new_token',
  'access_token',
  'refresh_token',
  'google_token',
  'stripe_api_key',
  'api_key',
  'secret',
  'client_secret',
  'authorization',
  'cookie',
  'set_cookie',
  'id_token',
}
# Oltre alle chiavi esatte, si nasconde qualsiasi chiave che contenga uno di
# questi pezzi (admin_password, confirm_password, webhook_secret, ...) o che
# finisca per _token: i nomi dei campi li sceglie ogni progetto, e una
# password con un nome nuovo non deve finire in chiaro nel log.
REDACTED_KEY_PARTS = ('password', 'secret')
REDACTED_KEY_SUFFIXES = ('_token',)
_ORDER_TRACKING_TOKEN = re.compile(r'(/order/(?:public|track)/)[A-Za-z0-9_-]+')
_ORDER_TRACKING_FRAGMENT = re.compile(r'(/order/track#)[A-Za-z0-9_-]+')


def is_redacted_key(key) -> bool:
  normalized = str(key).strip().lower().replace('-', '_')
  return (
    normalized in REDACTED_KEYS
    or any(part in normalized for part in REDACTED_KEY_PARTS)
    or normalized.endswith(REDACTED_KEY_SUFFIXES)
  )


def redact(value):
  if isinstance(value, dict):
    return {key: '***' if is_redacted_key(key) else redact(val) for key, val in value.items()}
  if isinstance(value, list):
    return [redact(item) for item in value]
  if isinstance(value, str):
    return _ORDER_TRACKING_FRAGMENT.sub(r'\1***', _ORDER_TRACKING_TOKEN.sub(r'\1***', value))
  return value


def parse_line(raw: bytes):
  raw = raw.strip()
  if not raw or len(raw) > LOG_MAX_LINE_BYTES:
    return None
  try:
    return json.loads(raw)
  except (json.JSONDecodeError, ValueError):
    return None


def log_default(o):
  return float(o) if isinstance(o, decimal.Decimal) else str(o)


def cap_request(request_info):
  if not isinstance(request_info, dict):
    return cap_field(request_info)

  return {key: value if key in ('method', 'path') else cap_field(value) for key, value in request_info.items()}


def strip_bodies(request_info, response):
  """Riduce richiesta e risposta a cio' che serve per l'audit, senza i body.

  Per gli endpoint che trattano credenziali o dati personali di chi non e'
  ancora un utente (login, cambio password, form pubblici) il log deve dire
  chi ha chiamato cosa e com'e' andata, non cosa e' stato mandato.
  """
  request_info = {key: request_info[key] for key in ('method', 'path') if key in request_info}
  if isinstance(response, dict):
    response = {key: response[key] for key in ('status', 'status_code', 'traceback') if key in response}
  else:
    response = None
  return request_info, response


def cap_field(value):
  if value is None:
    return None

  try:
    dumped = json.dumps(value, ensure_ascii=False, default=log_default)
  except Exception:
    return {'_truncated': True, 'error': 'non serializzabile'}

  if len(dumped) <= LOG_MAX_FIELD_CHARS:
    return value

  return {'_truncated': True, 'chars': len(dumped), 'preview': dumped[:2000]}
