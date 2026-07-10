import json
import decimal

from .paths import LOG_MAX_FIELD_CHARS, LOG_MAX_LINE_BYTES


REDACTED_KEYS = {
  'password',
  'new_password',
  'old_password',
  'pass_token',
  'token',
  'new_token',
  'google_token',
  'stripe_api_key',
}


def redact(value):
  if isinstance(value, dict):
    return {key: '***' if key.lower() in REDACTED_KEYS else redact(val) for key, val in value.items()}
  if isinstance(value, list):
    return [redact(item) for item in value]
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
