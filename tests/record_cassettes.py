"""Registra le cassette Telegram inviando i casi reali all'API (da lanciare a mano).

Uso:  TELEGRAM_TOKEN=<token> python tests/record_cassettes.py
Invia i messaggi di test al topic 'default' UNA volta e salva richieste/risposte
in tests/cassettes/. Da rilanciare solo quando cambiano i formati dei messaggi.
"""

# ruff: noqa: E402, T201
import os
import sys
import time
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TOKEN = os.environ.get('TELEGRAM_TOKEN')
if not TOKEN:
  raise SystemExit('Imposta TELEGRAM_TOKEN per registrare le cassette')

os.environ['PROJECT_NAME'] = 'default'

from telegram import Bot

from api import telegram as telegram_module
from tests.cassette import RecordingRequest, save_cassette
from tests.telegram_cases import CASES


def record_case(name: str, text: str) -> int:
  entries = []
  original_bot = telegram_module.Bot
  telegram_module.Bot = lambda token: Bot(token, request=RecordingRequest(TOKEN, entries))
  try:
    asyncio.run(telegram_module.send_message(text, topic_name='default'))
  finally:
    telegram_module.Bot = original_bot

  save_cassette(name, entries)
  return len(entries)


if __name__ == '__main__':
  for name, text in CASES:
    chunks = record_case(name, text)
    print(f'registrata cassetta {name}: {chunks} richieste')
    time.sleep(2)
