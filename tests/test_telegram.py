import threading

from api import telegram
from api.telegram import MAX_MESSAGE_LENGTH, MAX_TELEGRAM_TEXT, split_message


def test_split_message_short_text_single_chunk():
  assert split_message('breve') == ['breve']


def test_split_message_terminates_on_oversized_code_block():
  # Regressione: un blocco ``` più lungo di MAX_MESSAGE_LENGTH mandava split_message in loop infinito.
  message = 'header\n```\n' + '\n'.join(f'- {i}.png' for i in range(1500)) + '\n```'

  chunks = split_message(message)

  assert len(chunks) > 1
  assert all(chunks), 'nessun chunk vuoto'
  assert all(len(chunk) <= MAX_MESSAGE_LENGTH for chunk in chunks)


def test_split_message_keeps_code_fences_balanced_in_every_chunk():
  message = 'header\n```\n' + '\n'.join(f'- {i}.png' for i in range(1500)) + '\n```'

  for chunk in split_message(message):
    assert chunk.count('```') % 2 == 0, f'blocco di codice non chiuso nel chunk: {chunk[:60]}…'


def test_split_message_preserves_content():
  lines = [f'- {i}.png' for i in range(1500)]
  message = 'header\n```\n' + '\n'.join(lines) + '\n```'

  joined = '\n'.join(split_message(message))
  for line in lines:
    assert line in joined


def test_split_message_without_newlines_terminates():
  chunks = split_message('x' * (MAX_MESSAGE_LENGTH * 3))

  assert all(len(chunk) <= MAX_MESSAGE_LENGTH for chunk in chunks)
  assert sum(len(chunk) for chunk in chunks) == MAX_MESSAGE_LENGTH * 3


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


def test_escape_md_escapes_special_characters():
  escaped = telegram.escape_md('file_name (1).png')

  assert '\\_' in escaped
  assert '\\(' in escaped
  assert '\\)' in escaped
  assert '\\.' in escaped


def test_escape_md_preserves_balanced_bold_and_code():
  escaped = telegram.escape_md('*titolo*\n```\ncontenuto\n```')

  assert escaped.startswith('*titolo*')
  assert escaped.count('```') == 2
