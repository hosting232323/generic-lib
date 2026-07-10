import json
from datetime import datetime

from .dates import ROME_TZ
from .paths import get_log_dir
from ..telegram import extract_request_data
from .serialization import cap_request, cap_field, log_default, redact


DEFAULT_USER_LOG_FIELDS = ('email', 'nickname')


def write_log(user, log_folder, response=None, swagger=False, user_fields=DEFAULT_USER_LOG_FIELDS):
  request_info = extract_request_data(False)
  request_info.pop('headers', None)

  now = datetime.now(ROME_TZ)
  month_dir = get_log_dir(log_folder) / now.strftime('%Y-%m')
  month_dir.mkdir(parents=True, exist_ok=True)
  log_file = month_dir / f'{now.strftime("%Y-%m-%d")}.jsonl'
  user_identifier, user_identifier_field = get_user_identifier(user, swagger, user_fields)
  line = json.dumps(
    {
      'ts': now.isoformat(),
      'user_id': user.id if user else None,
      'nickname': user_identifier,
      'user_identifier': user_identifier,
      'user_identifier_field': user_identifier_field,
      'request': cap_request(redact(request_info)),
      'response': cap_field(redact(response)),
    },
    ensure_ascii=False,
    default=log_default,
  )

  with open(log_file, 'a', encoding='utf-8') as file:
    file.write(line)
    file.write('\n')


def get_user_identifier(user, swagger, user_fields=DEFAULT_USER_LOG_FIELDS):
  if user:
    for field in normalize_user_fields(user_fields):
      value = getattr(user, field, None)
      if value:
        return value, field
    return None, None
  return ('swagger', 'swagger') if swagger else (None, None)


def normalize_user_fields(user_fields):
  if isinstance(user_fields, str):
    return (user_fields,)
  return tuple(user_fields or DEFAULT_USER_LOG_FIELDS)
