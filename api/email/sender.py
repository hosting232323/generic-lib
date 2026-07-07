import os


EMAIL_SENDER = {
  'name': os.getenv('EMAIL_SENDER_NAME'),
  'address': os.getenv('EMAIL_SENDER_ADDRESS'),
  'login': os.getenv('EMAIL_SENDER_LOGIN') or os.getenv('EMAIL_SENDER_ADDRESS'),
  'password': os.getenv('EMAIL_SENDER_PASSWORD'),
  'smtp_server': os.getenv('EMAIL_SENDER_SMTP_SERVER'),
  'smtp_port': int(os.getenv('EMAIL_SENDER_SMTP_PORT', 587)),
  'max_retries': int(os.getenv('EMAIL_MAX_RETRIES', 3)),
  'retry_backoff': float(os.getenv('EMAIL_RETRY_BACKOFF', 2)),
}
