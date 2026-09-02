import asyncio
import threading

from flask import Flask
from telegramify_markdown import utf16_len

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
  assert all(utf16_len(chunk) <= MAX_MESSAGE_LENGTH for chunk in chunks)
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


def test_send_error_message_labels_and_orders_long_sections(monkeypatch):
  StubBot.sent = []
  monkeypatch.setattr(telegram, 'Bot', StubBot)
  trace = '\n'.join(f'trace line {index}' for index in range(800))
  request_data = '{\n' + ',\n'.join(f'  "field_{index}": "value"' for index in range(500)) + '\n}'

  asyncio.run(telegram.send_error_message(trace, request_data))

  chunks = chunk_texts(StubBot.sent)
  request_start = next(index for index, chunk in enumerate(chunks) if chunk.startswith('*Request Data'))
  assert request_start > 0
  assert all(chunk.startswith('*Errore') for chunk in chunks[:request_start])
  assert all(chunk.startswith('*Request Data') for chunk in chunks[request_start:])
  assert all(len(chunk) <= MAX_MESSAGE_LENGTH for chunk in chunks)
  assert ''.join(chunks).count('trace line') == 800
  assert ''.join(chunks).count('field_') == 500


def test_send_telegram_error_schedules_trace_and_request_as_separate_sections(monkeypatch):
  sent = []

  async def fake_send_error_message(trace, request_data=None):
    sent.append((trace, request_data))

  monkeypatch.setattr(telegram, 'IS_DEV', False)
  monkeypatch.setattr(telegram, 'TELEGRAM_TOKEN', 'test-token')
  monkeypatch.setattr(telegram, 'extract_request_data', lambda: '{"path": "/orders"}')
  monkeypatch.setattr(telegram, 'send_error_message', fake_send_error_message)
  monkeypatch.setattr(telegram, '_send_in_background', lambda coroutine_factory: asyncio.run(coroutine_factory()))

  telegram.send_telegram_error('traceback')

  assert sent == [('traceback', '{"path": "/orders"}')]


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


def test_send_telegram_message_does_not_interleave_background_batches(monkeypatch):
  events = []
  completed = threading.Event()
  created_threads = []
  real_thread = threading.Thread

  def recording_thread(*args, **kwargs):
    thread = real_thread(*args, **kwargs)
    created_threads.append(thread)
    return thread

  async def fake_send_message(text, topic_name=None):
    events.append(f'start:{text}')
    await asyncio.sleep(0.05)
    events.append(f'end:{text}')
    if len(events) == 4:
      completed.set()

  monkeypatch.setattr(telegram, 'send_message', fake_send_message)
  monkeypatch.setattr(telegram.threading, 'Thread', recording_thread)

  telegram.send_telegram_message('first')
  telegram.send_telegram_message('second')

  assert completed.wait(1)
  for thread in created_threads:
    thread.join(timeout=1)
  assert events in [
    ['start:first', 'end:first', 'start:second', 'end:second'],
    ['start:second', 'end:second', 'start:first', 'end:first'],
  ]


def test_extract_request_data_redacts_credentials_recursively():
  app = Flask(__name__)
  with app.test_request_context(
    '/orders?token=query-secret&visible=yes',
    method='POST',
    headers={
      'Authorization': 'Bearer header-secret',
      'Cookie': 'refresh_token=cookie-secret',
      'X-Api-Key': 'api-secret',
      'X-Request-Id': 'request-id',
    },
    json={'password': 'body-secret', 'nested': {'refresh_token': 'refresh-secret', 'value': 1}},
  ):
    request_data = telegram.extract_request_data(string_result=False)

  assert request_data['headers']['Authorization'] == telegram.REDACTED_VALUE
  assert request_data['headers']['Cookie'] == telegram.REDACTED_VALUE
  assert request_data['headers']['X-Api-Key'] == telegram.REDACTED_VALUE
  assert request_data['headers']['X-Request-Id'] == 'request-id'
  assert request_data['args'] == {'token': telegram.REDACTED_VALUE, 'visible': 'yes'}
  assert request_data['json'] == {
    'password': telegram.REDACTED_VALUE,
    'nested': {'refresh_token': telegram.REDACTED_VALUE, 'value': 1},
  }
