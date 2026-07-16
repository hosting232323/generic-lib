import os

from api import storage
from api.storage import check_mismatch
from api.storage.utils import MAX_MISMATCH_LINES, format_mismatch_message


def test_format_mismatch_message_no_mismatch():
  assert format_mismatch_message(['a.png'], ['a.png'], 'trovati {}', 'tutto ok') == ['tutto ok']


def test_format_mismatch_message_lists_sorted_mismatches():
  message = format_mismatch_message(['b.png', 'a.png', 'c.png'], ['c.png'], 'trovati {}', 'tutto ok')

  assert message == ['trovati 2', '```', '- a.png', '- b.png', '```']


def test_format_mismatch_message_truncates_long_lists():
  files = [f'{i:04}.png' for i in range(MAX_MISMATCH_LINES + 25)]

  message = format_mismatch_message(files, [], 'trovati {}', 'tutto ok')

  assert message[0] == f'trovati {MAX_MISMATCH_LINES + 25}'
  listed = [line for line in message if line.startswith('- ') and 'altri' not in line]
  assert len(listed) == MAX_MISMATCH_LINES
  assert '- … e altri 25 file' in message


def test_check_mismatch_compares_basenames_both_directions(tmp_path, monkeypatch):
  photos = tmp_path / 'test' / 'photos'
  os.makedirs(photos)
  (photos / 'a.png').write_bytes(b'x')
  (photos / 'orfano.png').write_bytes(b'x')

  messages = []
  monkeypatch.setattr(storage, 'send_telegram_message', lambda text, topic_name=None: messages.append(text))

  check_mismatch(['a.png', 'solo-db.png'], str(tmp_path), 'Photos', subfolder='photos')

  assert len(messages) == 1
  assert '- solo-db.png' in messages[0]
  assert '- orfano.png' in messages[0]
  assert '- a.png' not in messages[0]
