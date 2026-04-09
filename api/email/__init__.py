import smtplib
import traceback
from email.utils import formataddr
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from ..telegram import send_telegram_message
from .sender import EMAIL_SENDER


def send_email(receiver_email: str, body, subject: str, attachments: list = None):
  message = MIMEMultipart('alternative')
  message['From'] = formataddr((EMAIL_SENDER['name'], EMAIL_SENDER['address']))
  message['To'] = receiver_email
  message['Subject'] = subject

  if isinstance(body, dict) and 'text' in body and 'html' in body:
    text = body['text']
    html = body['html']
    part1 = MIMEText(text, 'plain')
    part2 = MIMEText(html, 'html')
    message.attach(part1)
    message.attach(part2)
  elif isinstance(body, str):
    part1 = MIMEText(body, 'plain')
    message.attach(part1)
  else:
    raise ValueError('Il corpo dell\'email deve essere un dizionario con le chiavi "text" e "html" o una stringa')

  if attachments:
    for attachment in attachments:
      part = MIMEApplication(attachment['content'])
      part.add_header('Content-Disposition', 'attachment', filename=attachment['filename'])
      message.attach(part)

  try:
    with smtplib.SMTP_SSL(EMAIL_SENDER['smtp_server'], EMAIL_SENDER['smtp_port']) as server:
      server.login(EMAIL_SENDER['address'], EMAIL_SENDER['password'])
      server.sendmail(EMAIL_SENDER['address'], receiver_email, message.as_string())
  except Exception:
    send_telegram_message(f'❌ Errore invio mail a {receiver_email}:\n```\n{traceback.format_exc()}\n```')
