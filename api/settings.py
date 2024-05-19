import sys

# Ignore error!
from src.constants import GENERIC_API_KEY


default_headers = {'Authorization': GENERIC_API_KEY}

hostname = (
  'https://generic-be.replit.app/'
  if len(sys.argv) > 1 and sys.argv[1] == '--production' else
  'http://127.0.0.1:8080/'
  if len(sys.argv) > 1 and sys.argv[1] == '--local' else
  'https://generic-be-test.replit.app/'
)
