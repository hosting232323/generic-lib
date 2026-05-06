import os
from dotenv import load_dotenv


load_dotenv()


API_PREFIX = os.environ.get('API_PREFIX')
SWAGGER_KEY = os.environ.get('SWAGGER_KEY')

SERVER_NAME = os.environ.get('SERVER_NAME', None)
BACKUP_FOLDER = os.environ.get('BACKUP_FOLDER', None)
RESTIC_PASSWORD = os.environ.get('RESTIC_PASSWORD', None)
BACKUP_SSH_CONFIG = os.environ.get('BACKUP_SSH_CONFIG', None)

IS_DEV = int(os.environ.get('IS_DEV', 1)) == 1
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'default')
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
