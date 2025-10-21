import sys
import time
from api.email import send_email


def spam_mail_main():
  content_path = sys.argv[1]
  contact_path = sys.argv[2]

  try:
    contacts_list = []
    with open(contact_path, 'r', encoding='utf-8') as email_file:
      headers = email_file.readline().strip().split(', ')  # Prima riga con i nomi dei campi
      for line in email_file:
        values = line.strip().split(', ')
        contact_dict = dict(zip(headers, values))  # Crea un dizionario per ogni riga
        contacts_list.append(contact_dict)
  except FileNotFoundError:
    print(f'Errore: Il file "{contact_path}" non è stato trovato.')
    return
  except Exception as e:
    print(f'Errore durante la lettura del file delle email: {e}')
    return

  try:
    with open(content_path, 'r', encoding='utf-8') as txt_file:
      txt_content = txt_file.read()
  except FileNotFoundError:
    print(f'Errore: Il file "{content_path}" non è stato trovato.')
    return
  except Exception as e:
    print(f'Errore durante la lettura del file del contenuto: {e}')
    return

  for i, contact in enumerate(contacts_list, start=1):
    try:
      email = contact.get('Email', 'nessuna_email')  # Recupera l'email dal dizionario
      personalized_email = txt_content

      for key, value in contact.items():
        personalized_email = personalized_email.replace(f'[{key}]', value if value else '')

        send_email(receiver_email=email, body=personalized_email, subject='Scopri i nostri servizi!')
        print(f'✅ Email inviata con successo a: {email} ({i}/{len(contacts_list)})')

        # Imposta un ritardo tra le email per evitare il blocco dello spam
        time.sleep(5)
    except Exception as e:
      print(f"❌ Errore nell'invio a {email}: {e}")
