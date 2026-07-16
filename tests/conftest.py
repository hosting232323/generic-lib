import os
import sys

# Le variabili vanno impostate prima di qualsiasi import di api: api.settings le legge a import-time.
os.environ['IS_DEV'] = '1'
os.environ['API_PREFIX'] = ''
os.environ['TELEGRAM_TOKEN'] = '123456:TEST-TOKEN'  # stesso valore di tests.cassette.FAKE_TOKEN
os.environ['PROJECT_NAME'] = 'default'

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
