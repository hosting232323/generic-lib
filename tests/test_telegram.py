import asyncio
import threading

from api import telegram
from api.telegram import MAX_MESSAGE_LENGTH, MAX_TELEGRAM_TEXT, TELEGRAM_TOPIC


class StubBot:
  sent = []

  def __init__(self, token):
    pass

  async def send_message(self, chat_id, text, message_thread_id, parse_mode):
    StubBot.sent.append({'text': text, 'topic': message_thread_id, 'chat_id': chat_id})


def send_and_collect(monkeypatch, text, topic_name=None):
  StubBot.sent = []
  monkeypatch.setattr(telegram, 'Bot', StubBot)
  asyncio.run(telegram.send_message(text, topic_name=topic_name))
  return StubBot.sent


def chunk_texts(sent):
  return [message['text'] for message in sent]


def test_send_message_short_text_single_chunk(monkeypatch):
  chunks = chunk_texts(send_and_collect(monkeypatch, 'messaggio breve'))

  assert len(chunks) == 1
  assert 'messaggio breve' in chunks[0]


def test_send_message_splits_oversized_code_block(monkeypatch):
  # Regressione: un report mismatch con un blocco ``` oltre i 4096 caratteri
  # mandava il vecchio split_message in loop infinito (thread appeso, zero errori).
  message = '*Report*\n```\n' + '\n'.join(f'- {i}.png' for i in range(1500)) + '\n```'

  chunks = chunk_texts(send_and_collect(monkeypatch, message))

  assert len(chunks) > 1
  assert all(chunks), 'nessun chunk vuoto'
  assert all(len(chunk) <= MAX_MESSAGE_LENGTH for chunk in chunks)
  assert ''.join(chunks).count('png') == 1500


def test_send_message_mismatch_report_shape(monkeypatch):
  # Il formato esatto prodotto da check_mismatch: grassetto, emoji e blocco di codice.
  message = (
    '*📊 Report Check Mismatch*\n▶️ Post File\n\n'
    '*❌ File presenti solo nel DB (2):*\n```\n- 1.png\n- 2.png\n```\n'
    '✔️ Nessun file solo in storage'
  )

  chunks = chunk_texts(send_and_collect(monkeypatch, message))

  assert len(chunks) == 1
  assert '1.png' in chunks[0]


def test_send_message_error_report_shape(monkeypatch):
  # Il formato di send_telegram_error: traceback e JSON con parentesi, underscore e apici.
  message = (
    '**Errore:**\n```\nTraceback (most recent call last):\n'
    '  File "/app/src/end_points/rae/__init__.py", line 12, in update_disposal\n'
    "    raise ValueError('FIR gia_ presente [id=3]')\n```\n\n"
    '**Request Data:**\n```json\n{"path": "/api/checks", "method": "GET"}\n```'
  )

  chunks = chunk_texts(send_and_collect(monkeypatch, message))

  assert len(chunks) == 1
  assert 'Traceback' in chunks[0]


def test_send_message_unbalanced_markdown_does_not_raise(monkeypatch):
  # Il bug storico del bold: markdown sbilanciato nei nomi file non deve rompere l'invio.
  chunks = chunk_texts(send_and_collect(monkeypatch, 'file_name *incompleto [strano].png con `backtick'))

  assert len(chunks) == 1


def test_send_message_routes_to_requested_topic(monkeypatch):
  sent = send_and_collect(monkeypatch, 'test', topic_name='italco-be')

  assert sent[0]['topic'] == TELEGRAM_TOPIC['italco-be']


def test_send_message_unknown_topic_falls_back_to_default(monkeypatch):
  sent = send_and_collect(monkeypatch, 'test', topic_name='progetto-inesistente')

  assert sent[0]['topic'] == TELEGRAM_TOPIC['default']


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
