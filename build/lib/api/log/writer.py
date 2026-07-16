import json
from datetime import datetime

from .dates import ROME_TZ
from .paths import get_log_dir
from ..telegram import extract_request_data
from .serialization import cap_request, cap_field, log_default, redact


DEFAULT_USER_LOG_FIELD = 'email'


def write_log(user, log_folder, response=None, swagger=False, user_field=DEFAULT_USER_LOG_FIELD):
  request_info = extract_request_data(False)
  request_info.pop('headers', None)

  now = datetime.now(ROME_TZ)
  month_dir = get_log_dir(log_folder) / now.strftime('%Y-%m')
  month_dir.mkdir(parents=True, exist_ok=True)
  log_file = month_dir / f'{now.strftime("%Y-%m-%d")}.jsonl'
  line = json.dumps(
    {
      'ts': now.isoformat(),
      'user_id': user.id if user else None,
      'identifier': get_user_identifier(user, swagger, user_field),
      'request': cap_request(redact(request_info)),
      'response': cap_field(redact(response)),
    },
    ensure_ascii=False,
    default=log_default,
  )

  with open(log_file, 'a', encoding='utf-8') as file:
    file.write(line)
    file.write('\n')


def get_user_identifier(user, swagger, user_field=DEFAULT_USER_LOG_FIELD):
  if user:
    field = user_field or DEFAULT_USER_LOG_FIELD
    return getattr(user, field, None)

  return 'swagger' if swagger else None
