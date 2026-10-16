"""Quali chiavi di un payload sono segreti da non mostrare.

Unica regola per i log delle richieste (`api.log.serialization.redact`) e per i
dati di richiesta mandati su Telegram (`api.telegram`): una lista sola, cosi'
le due strade non possono divergere. Il modulo non importa niente del
pacchetto, per non creare import circolari fra `log` e `telegram`.

Una chiave e' segreta se, ridotta in snake_case minuscolo (`accessToken`,
`Access-Token` e `ACCESS_TOKEN` diventano tutte `access_token`):
- e' fra `SECRET_KEYS`, oppure
- contiene `password` o `secret` (admin_password, clientSecret, ...), oppure
- finisce per `_token` (device_token, idToken, ...).

Falsi positivi voluti: anche campi innocui come `has_password`,
`password_changed_at` o `password_expired` diventano `***`. Meglio nascondere
un booleano in piu' che lasciare in chiaro una password con un nome nuovo:
leggendo i log, un `***` su questi campi non e' un errore.
"""

import re


SECRET_KEYS = frozenset(
  {
    'access_token',
    'api_key',
    'authorization',
    'client_secret',
    'cookie',
    'google_token',
    'id_token',
    'new_password',
    'new_token',
    'old_password',
    'pass_token',
    'password',
    'proxy_authorization',
    'refresh_token',
    'secret',
    'set_cookie',
    'stripe_api_key',
    'swagger_authorization',
    'token',
    'x_api_key',
    'x_auth_token',
  }
)
SECRET_KEY_PARTS = ('password', 'secret')
SECRET_KEY_SUFFIXES = ('_token',)

_CAMEL_BOUNDARY = re.compile(r'([a-z0-9])([A-Z])')
_ACRONYM_BOUNDARY = re.compile(r'([A-Z]+)([A-Z][a-z])')


def normalize_key(key) -> str:
  """`accessToken`, `Access-Token`, `APIKey` -> `access_token`, `access_token`, `api_key`."""
  text = str(key).strip().replace('-', '_')
  text = _ACRONYM_BOUNDARY.sub(r'\1_\2', text)
  text = _CAMEL_BOUNDARY.sub(r'\1_\2', text)
  return text.lower()


def is_secret_key(key) -> bool:
  normalized = normalize_key(key)
  return (
    normalized in SECRET_KEYS
    or any(part in normalized for part in SECRET_KEY_PARTS)
    or normalized.endswith(SECRET_KEY_SUFFIXES)
  )
