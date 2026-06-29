from pathlib import Path

from ..settings import IS_DEV


INDEX_SUFFIX = '.idx'
LOG_MAX_FIELD_CHARS = 50_000
LOG_MAX_LINE_BYTES = 1_000_000


def get_log_dir(static_folder) -> Path:
  log_dir = Path(static_folder) / ('test' if IS_DEV else 'prod') / 'logs'
  log_dir.mkdir(parents=True, exist_ok=True)
  return log_dir
