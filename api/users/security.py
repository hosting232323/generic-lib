import os
import base64
import hashlib

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from werkzeug.security import generate_password_hash, check_password_hash


# Chiave usata per la copia reversibile della password (feature "mostra
# password" lato admin). Sta SOLO nel backend (env), mai nel bundle FE. La
# passphrase viene derivata a 32 byte con sha256, cosi' puo' essere una
# stringa qualsiasi.
PASSWORD_SHADOW_KEY = os.environ.get('PASSWORD_SHADOW_KEY')


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


def _shadow_key() -> bytes:
  if not PASSWORD_SHADOW_KEY:
    raise RuntimeError('PASSWORD_SHADOW_KEY non configurata')
  return hashlib.sha256(PASSWORD_SHADOW_KEY.encode('utf-8')).digest()


def encrypt_reversible(plain: str) -> str:
  key = _shadow_key()
  iv = os.urandom(16)

  padder = padding.PKCS7(128).padder()
  padded = padder.update(plain.encode('utf-8')) + padder.finalize()

  encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
  ciphertext = encryptor.update(padded) + encryptor.finalize()
  return base64.b64encode(iv + ciphertext).decode('utf-8')


def decrypt_reversible(token: str) -> str:
  key = _shadow_key()
  raw = base64.b64decode(token)
  iv, ciphertext = raw[:16], raw[16:]

  decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
  padded = decryptor.update(ciphertext) + decryptor.finalize()

  unpadder = padding.PKCS7(128).unpadder()
  return (unpadder.update(padded) + unpadder.finalize()).decode('utf-8')
