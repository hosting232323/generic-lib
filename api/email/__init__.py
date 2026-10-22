import base64
import time
import traceback

import requests

from .sender import EMAIL_SENDER, RESEND_API_KEY
from ..telegram import send_telegram_message


RESEND_API_URL = 'https://api.resend.com/emails'
RETRY_BACKOFF = 2.0
SMTP_MAX_RETRIES = 3


def send_email(
  receiver_email: str,
  body,
  subject: str,
  attachments: list = None,
  signature: dict | str = None,
  tag: str = None,
  sender: dict = None,
  reply_to: str = None,
  headers: dict = None,
) -> str | None:
  """
  Invia una mail tramite Resend API.

  `sender` ({'name', 'address'}) sostituisce il mittente di configurazione
  (EMAIL_SENDER_*) per questa sola mail; `reply_to` e `headers` (es.
  In-Reply-To, References, List-Unsubscribe) passano com'e' a Resend.

  Ritorna l'email_id Resend (str) se la mail è accettata, None se tutti i
  tentativi falliscono (invia anche alert Telegram in quel caso).

  Backward-compatible con il vecchio bool: None è falsy come False, una
  stringa non vuota è truthy come True. I chiamanti che fanno `if send_email(...)`
  continuano a funzionare senza modifiche; quelli che vogliono tracciare la
  consegna (italco-be/mailer.py) usano l'email_id restituito come chiave di
  correlazione con i webhook Resend.
  """
  payload = _build_payload(receiver_email, body, subject, attachments, signature, tag, sender, reply_to, headers)

  attempts = max(1, SMTP_MAX_RETRIES)
  backoff = RETRY_BACKOFF
  last_error = None

  for attempt in range(1, attempts + 1):
    try:
      return _deliver(payload)
    except Exception:
      last_error = traceback.format_exc()
      if attempt < attempts:
        time.sleep(backoff * attempt)

  send_telegram_message(_build_error_message(receiver_email, subject, body, last_error))
  return None


def _build_payload(
  receiver_email: str,
  body,
  subject: str,
  attachments: list = None,
  signature: dict | str = None,
  tag: str = None,
  sender: dict = None,
  reply_to: str = None,
  headers: dict = None,
) -> dict:
  sig_text = ''
  sig_html = ''
  if signature:
    if isinstance(signature, dict):
      sig_text = signature.get('text', '')
      sig_html = signature.get('html', '')
    elif isinstance(signature, str):
      sig_text = signature

  sender = sender or EMAIL_SENDER
  payload: dict = {
    'from': f'{sender["name"]} <{sender["address"]}>' if sender.get('name') else sender['address'],
    'to': [receiver_email],
    'subject': subject,
  }

  if isinstance(body, dict) and 'text' in body and 'html' in body:
    payload['text'] = body['text'] + (f'\n\n{sig_text}' if sig_text else '')
    payload['html'] = body['html'] + (f'<br><br>{sig_html}' if sig_html else '')
  elif isinstance(body, str):
    payload['text'] = body + (f'\n\n{sig_text}' if sig_text else '')
  else:
    raise ValueError('Il corpo dell\'email deve essere un dizionario con le chiavi "text" e "html" o una stringa')

  if attachments:
    payload['attachments'] = [_build_attachment(a) for a in attachments]

  if reply_to:
    payload['reply_to'] = reply_to

  headers = {key: value for key, value in (headers or {}).items() if value}
  if headers:
    payload['headers'] = headers

  if tag:
    # Resend tags: array di {name, value}. Sono key-value alfanumerici.
    # Utili per filtrare nella dashboard Resend; la correlazione webhook avviene
    # tramite l'email_id restituito da _deliver(), non via questo campo.
    safe_tag = ''.join(c if c.isalnum() or c == '-' else '-' for c in str(tag))[:128]
    payload['tags'] = [{'name': 'tag', 'value': safe_tag or 'unset'}]

  return payload


def _build_attachment(attachment: dict) -> dict:
  content = attachment['content']
  if isinstance(content, bytes):
    content = base64.b64encode(content).decode('ascii')

  result: dict = {
    'filename': attachment['filename'],
    'content': content,
  }

  # Resend deduce il content-type dal filename se non viene passato esplicitamente.
  # Lo propaghiamo solo se il chiamante lo ha fornito per evitare di passare
  # un valore None che l'API potrebbe rifiutare.
  if attachment.get('content_type'):
    result['content_type'] = attachment['content_type']

  return result


def _deliver(payload: dict) -> str:
  """
  Chiama POST https://api.resend.com/emails e restituisce l'email_id.

  Solleva un'eccezione su qualsiasi risposta non-2xx (incluso 422 per dominio
  non verificato, 429 per limite giornaliero superato, ecc.) — l'errore è
  esplicito e immediato, mai silenzioso come la coda del piano Free di Brevo.
  """
  response = requests.post(
    RESEND_API_URL,
    json=payload,
    headers={
      'Authorization': f'Bearer {RESEND_API_KEY}',
      'Content-Type': 'application/json',
    },
    timeout=30,
  )
  response.raise_for_status()
  return response.json()['id']


def _build_error_message(receiver_email: str, subject: str, body, error: str) -> str:
  return (
    f'❌ *Errore invio mail a* `{receiver_email}`\n'
    f'*Subject:* {subject}\n\n'
    f'*Contenuto della mail:*\n{_extract_body_text(body)}\n\n'
    f'```\n{error}\n```'
  )


def _extract_body_text(body) -> str:
  if isinstance(body, dict):
    return body.get('text') or body.get('html') or ''
  return body or ''
