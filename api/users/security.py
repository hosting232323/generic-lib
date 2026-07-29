from werkzeug.security import generate_password_hash, check_password_hash


def hash_password(raw_password: str) -> str:
  return generate_password_hash(raw_password)


def is_hashed(stored: str) -> bool:
  return bool(stored) and '$' in stored and ':' in stored


def verify_password(raw_password: str, stored: str) -> bool:
  if not stored:
    return False
  if not is_hashed(stored):
    return stored == raw_password
  return check_password_hash(stored, raw_password)
