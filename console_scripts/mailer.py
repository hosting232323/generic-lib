import sys
import time

from api.email import send_email


def spam_mail_main():
  content_path = sys.argv[1]
  contact_path = sys.argv[2]

  try:
    emails_dict = {}
    with open(contact_path, 'r', encoding='utf-8') as email_file:
      for line in email_file:
        if line.strip():
          email, surname = line.strip().split(', ')
          emails_dict[email] = surname
  except FileNotFoundError:
    print(f"Errore: Il file '{contact_path}' non è stato trovato.")
    return
  except Exception as e:
    print(f"Errore durante la lettura del file delle email: {e}")
    return

  try:
    with open(content_path, 'r', encoding='utf-8') as txt_file:
      txt_content = txt_file.read()
  except FileNotFoundError:
    print(f"Errore: Il file '{content_path}' non è stato trovato.")
    return
  except Exception as e:
    print(f"Errore durante la lettura del file del contenuto: {e}")
    return

  for i, (email, cognome) in enumerate(emails_dict.items(), start=1):
    try:
      email_personalizzato = txt_content.replace("[Cognome]", cognome)
      
      send_email(
        receiver_email=email,
        body=email_personalizzato,
        subject="Scopri i nostri servizi!"
      )
      print(f'✅ Email inviata con successo a: {email} ({i}/{len(emails_dict)})')

      # Imposta un ritardo tra le email per evitare il blocco dello spam
      time.sleep(5)
    except Exception as e:
      print(f'❌ Errore nell\'invio a {email}: {e}')
