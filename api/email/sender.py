import os


EMAIL_SENDER = {
  'name': os.getenv('EMAIL_SENDER_NAME'),
  'address': os.getenv('EMAIL_SENDER_ADDRESS'),
  'login': os.getenv('EMAIL_SENDER_LOGIN'),
  'password': os.getenv('EMAIL_SENDER_PASSWORD')
}
