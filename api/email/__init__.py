import time
import smtplib
import traceback
from email.utils import formataddr
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

from .sender import EMAIL_SENDER
from ..telegram import send_telegram_message


SMTP_PORT = 587
RETRY_BACKOFF = 2.0
SMTP_MAX_RETRIES = 3
SMTP_SERVER = 'smtp-relay.brevo.com'


def send_email(receiver_email: str, body, subject: str, attachments: list = None, signature: dict | str = None) -> bool:
  message = _build_message(receiver_email, body, subject, attachments, signature)
  raw = message.as_string()

  attempts = max(1, SMTP_MAX_RETRIES)
  backoff = RETRY_BACKOFF
  last_error = None

  for attempt in range(1, attempts + 1):
    try:
      _deliver(receiver_email, raw)
      return True
    except Exception:
      last_error = traceback.format_exc()
      if attempt < attempts:
        time.sleep(backoff * attempt)

  send_telegram_message(_build_error_message(receiver_email, subject, body, last_error))
  return False


def _build_message(
  receiver_email: str, body, subject: str, attachments: list = None, signature: dict | str = None
) -> MIMEMultipart:
  message = MIMEMultipart('alternative')
  message['From'] = formataddr((EMAIL_SENDER['name'], EMAIL_SENDER['address']))
  message['To'] = receiver_email
  message['Subject'] = subject

  sig_text = ''
  sig_html = ''
  if signature:
    if isinstance(signature, dict):
      sig_text = signature.get('text', '')
      sig_html = signature.get('html', '')
    elif isinstance(signature, str):
      sig_text = signature

  if isinstance(body, dict) and 'text' in body and 'html' in body:
    body_text = body['text'] + (f'\n\n{sig_text}' if sig_text else '')
    body_html = body['html'] + (f'<br><br>{sig_html}' if sig_html else '')
    message.attach(MIMEText(body_text, 'plain'))
    message.attach(MIMEText(body_html, 'html'))
  elif isinstance(body, str):
    body_text = body + (f'\n\n{sig_text}' if sig_text else '')
    message.attach(MIMEText(body_text, 'plain'))
  else:
    raise ValueError('Il corpo dell\'email deve essere un dizionario con le chiavi "text" e "html" o una stringa')

  if attachments:
    for attachment in attachments:
      part = MIMEApplication(attachment['content'])
      part.add_header('Content-Disposition', 'attachment', filename=attachment['filename'])
      message.attach(part)

  return message


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


def _connect() -> smtplib.SMTP:
  server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
  server.ehlo()
  server.starttls()
  server.ehlo()
  server.login(EMAIL_SENDER['login'], EMAIL_SENDER['password'])
  return server


def _deliver(receiver_email: str, raw: str) -> None:
  with _connect() as server:
    server.sendmail(EMAIL_SENDER['address'], receiver_email, raw)
