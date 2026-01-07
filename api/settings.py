import os
from dotenv import load_dotenv


load_dotenv()


SWAGGER_KEY = os.environ.get('SWAGGER_KEY')
IS_DEV = int(os.environ.get('IS_DEV', 1)) == 1
API_PREFIX = os.environ.get('API_PREFIX', None)
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'default')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
