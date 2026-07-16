import asyncio

import pytest
from telegram import Bot

from api import telegram
from api.telegram import CHAT_ID, MAX_MESSAGE_LENGTH, TELEGRAM_TOPIC
from tests.cassette import ReplayRequest, load_cassette
from tests.telegram_cases import CASES


@pytest.mark.parametrize('name,text', CASES, ids=[name for name, _ in CASES])
def test_send_message_replays_recorded_api_interaction(monkeypatch, name, text):
  entries = load_cassette(name)
  replay = ReplayRequest(entries)
  monkeypatch.setattr(telegram, 'Bot', lambda token: Bot(token, request=replay))

  asyncio.run(telegram.send_message(text, topic_name='default'))

  assert replay.played == len(entries), 'non tutte le richieste registrate sono state riprodotte'
  for entry in entries:
    assert entry['params']['chat_id'] == CHAT_ID
    assert entry['params']['message_thread_id'] == TELEGRAM_TOPIC['default']
    assert entry['params']['parse_mode'] == 'MarkdownV2'
    assert len(entry['params']['text']) <= MAX_MESSAGE_LENGTH


def test_oversized_report_cassette_has_multiple_chunks():
  entries = load_cassette('blocco_codice_gigante')

  assert len(entries) > 1
  assert ''.join(entry['params']['text'] for entry in entries).count('png') == 1200
