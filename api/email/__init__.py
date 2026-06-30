import os
import urllib.error
import json as _json
import urllib.request

from ..telegram import send_telegram_message


def send_email(to: str, subject: str, body: str, from_address: str = 'noreply@fastsite.it'):
  api_key = os.getenv('RESEND_API_KEY')
  if not api_key:
    raise RuntimeError('RESEND_API_KEY non impostata')

  payload = _json.dumps(
    {
      'from': from_address,
      'to': [to],
      'subject': subject,
      'text': body,
    }
  ).encode('utf-8')

  req = urllib.request.Request(
    'https://api.resend.com/emails',
    data=payload,
    headers={
      'Authorization': f'Bearer {api_key}',
      'Content-Type': 'application/json',
    },
    method='POST',
  )

  try:
    with urllib.request.urlopen(req) as resp:
      if resp.status not in (200, 201):
        raise RuntimeError(f'Resend ha risposto {resp.status}')
  except urllib.error.HTTPError as exc:
    error_body = exc.read().decode('utf-8', errors='replace')
    send_telegram_message(f'❌ Errore Resend invio mail a {to} — {exc.code}:\n```{error_body}```')
