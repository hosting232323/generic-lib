import os
from dotenv import load_dotenv


load_dotenv()


API_PREFIX = os.environ.get('API_PREFIX')
SWAGGER_KEY = os.environ.get('SWAGGER_KEY')

SFTP_USER = os.environ.get('SFTP_USER', None)
SFTP_HOST = os.environ.get('SFTP_HOST', None)
SERVER_NAME = os.environ.get('SERVER_NAME', None)
BACKUP_FOLDER = os.environ.get('BACKUP_FOLDER', None)
RESTIC_PASSWORD = os.environ.get('RESTIC_PASSWORD', None)

IS_DEV = int(os.environ.get('IS_DEV', 1)) == 1
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'default')

SFTP_USER = os.environ.get('SFTP_USER')
SFTP_HOST = os.environ.get('SFTP_HOST')
SERVER_NAME = os.environ.get('SERVER_NAME')
BACKUP_FOLDER = os.environ.get('BACKUP_FOLDER')
RESTIC_PASSWORD = os.environ.get('RESTIC_PASSWORD')
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
