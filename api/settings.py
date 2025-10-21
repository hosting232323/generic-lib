import sys


hostname = (
  'https://generic-be.replit.app/'
  if '--production' in sys.argv
  else 'http://127.0.0.1:8080/'
  if '--local' in sys.argv
  else 'https://generic-be-test.replit.app/'
)
