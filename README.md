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

Install python on your computer
```bash
https://www.python.org
```
Install the library
```bash
pip install git+https://github.com/hosting232323/generic-lib.git
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
#### 1. Contacts File (contact_content_file.txt)
This file must contain a list of contacts with the following rules:
- The first line is mandatory and must contain the headers.
- It must start with Email, followed by any other fields such as Name, Surname, etc.
- Values ​​must be separated by a comma followed by a space (, ).
- The file_contact_content_mail.txt file can contain fields such as [Name], [Surname], etc.
- The header of the file_contact_content.txt file must necessarily start with Email

Correct file example
```bash
Email, Name, Surname
mario.rossi@email.com, Mario, Rossi
giulia.bianchi@email.com, Giulia, Bianchi
luca.verdi@email.com, Luca, 
```
If a value is missing, leave the blank space after the comma.

#### 2. Email Content File (mail_content_file.txt)
This file contains the email text and may include customizable placeholders enclosed in [ ], such as [First Name], [Last Name], etc.
These placeholders will be automatically replaced with the corresponding values ​​from your contacts file.

Example of email content:
```css
Hi [First Name] [Last Name],

We are happy to inform you about our new exclusive offers.
Find out more by visiting our website!

See you soon,
The Team
```
Result for a specific recipient:

```css
Hi John Smith,

We are happy to inform you about our new exclusive offers.
Find out more by visiting our website!

See you soon,
The Team
```
If a field in your contacts file is missing (e.g. missing Last Name), the placeholder will be automatically removed.

----
Open CMD and run the script
```bash
 spam_mail file_contenuto_mail.txt file_contenuto_contatti.txt
```

## Basic commands to run changes after you have already set up the project and started the virtual environment (venv)

```bash
python -m build
pip install .\dist\generic_lib-<version>.tar.gz[other]
nome metodo creato su setup.cfg
```