# Generic Lib

Build command: `python -m build`

## Setup Project

```bash
python -m venv venv

.\venv\Scripts\activate

pip install generic_lib-<version>.tar.gz

setup_project <generic_api_key>
```

## Console scripts

```bash
# Database export
db_export <database_url>

# Database import
db_import <database_url> <backup_file>
```

## Running project options

Basic run with deployed test instance of generic-be on https://generic-be-test.replit.app/
```bash
python -m src
```

Run with local instance of generic-be on http://127.0.0.1:8080/
```bash
python -m src --local
```

Run with deployed produciton instance of generic-be on https://generic-be.replit.app/ and with automatic backup saved on git
```bash
python -m src --production
```

## Api

```python
# Mail
from api import send_mail
# User
from api import register_user, login, ask_change_password, change_password, session_token_decorator
# Storage
from api import download_file, upload_file # da deprecare?
```

## Database api

```python
from database_api import Session, set_database
from database_api.operations import create, update, delete, get_by_id
```

## Mailer

```bash
pip install generic_lib-<version>.tar.gz
```
Set environment variables by opening CMD as administrator
```bash
setx EMAIL_SENDER_NAME "IlTuoNome" /M
setx EMAIL_SENDER_ADDRESS "seller@fastsite.it" /M
setx EMAIL_SENDER_PASSWORD "Nj7U&C3AC+Q5" /M
setx EMAIL_SENDER_SMTP_SERVER "smtps.aruba.it" /M
```
Add to PATH in environment variables
```bash
C:\Users\...\AppData\Roaming\Python\Python312\Scripts
```
Open CMD and run the script
```bash
 spam_mail file_contenuto_mail file_contenuto_contatti
```

## Comandi base per runnare modifiche dopo aver già impostato il progetto e avviato il virtual environment (venv)

```bash
python -m build
pip install .\dist\generic_lib-<version>.tar.gz[other]
nome metodo creato su setup.cfg
```