import asyncio
import threading

from api import telegram
from api.telegram import MAX_MESSAGE_LENGTH, MAX_TELEGRAM_TEXT


class StubBot:
  sent = []

  def __init__(self, token):
    pass

  async def send_message(self, chat_id, text, message_thread_id, parse_mode):
    StubBot.sent.append(text)


def send_and_collect(monkeypatch, text):
  StubBot.sent = []
  monkeypatch.setattr(telegram, 'Bot', StubBot)
  asyncio.run(telegram.send_message(text))
  return StubBot.sent


def test_send_message_short_text_single_chunk(monkeypatch):
  chunks = send_and_collect(monkeypatch, 'messaggio breve')

  assert len(chunks) == 1
  assert 'messaggio breve' in chunks[0]


def test_send_message_splits_oversized_code_block(monkeypatch):
  # Regressione: un report mismatch con un blocco ``` oltre i 4096 caratteri
  # mandava il vecchio split_message in loop infinito (thread appeso, zero errori).
  message = '*Report*\n```\n' + '\n'.join(f'- {i}.png' for i in range(1500)) + '\n```'

  chunks = send_and_collect(monkeypatch, message)

  assert len(chunks) > 1
  assert all(chunks), 'nessun chunk vuoto'
  assert all(len(chunk) <= MAX_MESSAGE_LENGTH for chunk in chunks)
  assert ''.join(chunks).count('png') == 1500


def test_send_message_special_characters_do_not_break(monkeypatch):
  chunks = send_and_collect(monkeypatch, '*Report* file_name (1).png [ok] `codice`')

  assert len(chunks) == 1


def test_send_telegram_message_truncates_oversized_text(monkeypatch):
  sent = []

  async def fake_send_message(text, topic_name=None):
    sent.append(text)

  class InlineThread:
    def __init__(self, target, daemon=None):
      self._target = target

    def start(self):
      self._target()

  monkeypatch.setattr(telegram, 'send_message', fake_send_message)
  monkeypatch.setattr(threading, 'Thread', InlineThread)

  telegram.send_telegram_message('x' * (MAX_TELEGRAM_TEXT * 2))

  assert len(sent) == 1
  assert sent[0].endswith('… messaggio troncato')
  assert len(sent[0]) <= MAX_TELEGRAM_TEXT + len('\n… messaggio troncato')
