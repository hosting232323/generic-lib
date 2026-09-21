import os


EMAIL_SENDER = {
  'name': os.getenv('EMAIL_SENDER_NAME'),
  'address': os.getenv('EMAIL_SENDER_ADDRESS'),
}

# API key Resend (https://resend.com/api-keys).
# Ogni progetto ha la propria variabile d'ambiente che punta al proprio account
# Resend (es. Italco → account Resend Italco, FastSite → account Resend FastSite)
# così i 100 mail/giorno free non sono condivisi.
RESEND_API_KEY = os.getenv('RESEND_API_KEY')
