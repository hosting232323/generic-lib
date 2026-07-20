import os
import sys

# Le variabili vanno impostate prima di qualsiasi import di api: api.settings le legge a import-time.
os.environ['IS_DEV'] = '1'
os.environ['API_PREFIX'] = ''
os.environ['TELEGRAM_TOKEN'] = '123456:TEST-TOKEN'  # stesso valore di tests.cassette.FAKE_TOKEN
os.environ['PROJECT_NAME'] = 'default'
os.environ.setdefault('DECODE_JWT_TOKEN', 'test_jwt_secret_key_for_session_auth')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
