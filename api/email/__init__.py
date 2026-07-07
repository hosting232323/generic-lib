import time
import smtplib
import traceback
from email.utils import formataddr
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

from .sender import EMAIL_SENDER
from ..telegram import send_telegram_message


def _build_message(receiver_email: str, body, subject: str, attachments: list = None) -> MIMEMultipart:
  message = MIMEMultipart('alternative')
  message['From'] = formataddr((EMAIL_SENDER['name'], EMAIL_SENDER['address']))
  message['To'] = receiver_email
  message['Subject'] = subject

  if isinstance(body, dict) and 'text' in body and 'html' in body:
    message.attach(MIMEText(body['text'], 'plain'))
    message.attach(MIMEText(body['html'], 'html'))
  elif isinstance(body, str):
    message.attach(MIMEText(body, 'plain'))
  else:
    raise ValueError('Il corpo dell\'email deve essere un dizionario con le chiavi "text" e "html" o una stringa')

  if attachments:
    for attachment in attachments:
      part = MIMEApplication(attachment['content'])
      part.add_header('Content-Disposition', 'attachment', filename=attachment['filename'])
      message.attach(part)

  return message


def _connect() -> smtplib.SMTP:
  server = smtplib.SMTP(EMAIL_SENDER['smtp_server'], EMAIL_SENDER['smtp_port'])
  server.ehlo()
  server.starttls()
  server.ehlo()
  server.login(EMAIL_SENDER['login'], EMAIL_SENDER['password'])
  return server


def _deliver(receiver_email: str, raw: str) -> None:
  with _connect() as server:
    server.sendmail(EMAIL_SENDER['address'], receiver_email, raw)


def send_email(receiver_email: str, body, subject: str, attachments: list = None) -> bool:
  message = _build_message(receiver_email, body, subject, attachments)
  raw = message.as_string()

  attempts = max(1, EMAIL_SENDER['max_retries'])
  backoff = EMAIL_SENDER['retry_backoff']
  last_error = None

  for attempt in range(1, attempts + 1):
    try:
      _deliver(receiver_email, raw)
      return True
    except Exception:
      last_error = traceback.format_exc()
      if attempt < attempts:
        time.sleep(backoff * attempt)

  send_telegram_message(f'❌ *Errore invio mail a* `{receiver_email}`\n*Subject:* {subject}\n```\n{last_error}\n```')
  return False
