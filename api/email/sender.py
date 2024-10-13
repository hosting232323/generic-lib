import os

EMAIL_SENDER = {
  'smtp_port': 465,
  'name': os.getenv('EMAIL_SENDER_NAME'),
  'address': os.getenv('EMAIL_SENDER_ADDRESS'),
  'password': os.getenv('EMAIL_SENDER_PASSWORD'),
  'smtp_server': os.getenv('EMAIL_SENDER_SMTP_SERVER')
}
