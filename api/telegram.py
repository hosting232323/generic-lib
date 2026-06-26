import json
import asyncio
import threading
from telegram import Bot
from flask import request

from .settings import IS_DEV, TELEGRAM_TOKEN, PROJECT_NAME


CHAT_ID = -1003410500390
TELEGRAM_TOPIC = {
  'default': 4294967440,
  'lotec-be': 4294968233,
  'wooffy-be': 4294967352,
  'italco-be': 4294967355,
  'chatty-be': 4294967354,
  'generic-be': 4294967350,
  'strongbox-be': 4294967353,
  'generic-be-demo': 4294967664,
  'generic-booking': 4294967351,
}
MAX_MESSAGE_LENGTH = 4096


loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)


def start_loop(loop):
  asyncio.set_event_loop(loop)
  loop.run_forever()


threading.Thread(target=start_loop, args=(loop,), daemon=True).start()


def escape_md(text: str) -> str:
  has_bold = (text.count('*') % 2 == 0) and (text.count('*') > 0)
  triple_count = text.count('```')
  has_triple = (triple_count % 2 == 0) and (triple_count > 0)
  inline_count = text.replace('```', '').count('`')
  has_inline = (inline_count % 2 == 0) and (inline_count > 0)

  result = []
  i = 0
  n = len(text)
  inside_code_block = False
  inside_inline_code = False
  inside_bold = False

  while i < n:
    if has_triple and i + 2 < n and text[i : i + 3] == '```':
      if not inside_inline_code:
        inside_code_block = not inside_code_block
        result.append('```')
        i += 3
        continue
    if has_inline and text[i] == '`':
      if not inside_code_block:
        inside_inline_code = not inside_inline_code
        result.append('`')
        i += 1
        continue
    if has_bold and text[i] == '*':
      if not inside_code_block and not inside_inline_code:
        inside_bold = not inside_bold
        result.append('*')
        i += 1
        continue
    ch = text[i]
    if inside_code_block or inside_inline_code:
      if ch in ('\\', '`'):
        result.append('\\' + ch)
      else:
        result.append(ch)
    else:
      escape_chars = r'\_[]()~>#+-=|{}.!'
      if not has_bold:
        escape_chars += '*'
      if not has_inline:
        escape_chars += '`'
      if ch in escape_chars:
        result.append('\\' + ch)
      elif ch == '*' and has_bold:
        result.append('\\*')
      elif ch == '`' and has_inline:
        result.append('\\`')
      else:
        result.append(ch)
    i += 1
  return ''.join(result)


async def send_message(text, topic_name=None):
  escaped_text = escape_md(text)
  for chunk in split_message(escaped_text):
    await Bot(TELEGRAM_TOKEN).send_message(
      chat_id=CHAT_ID,
      text=chunk,
      message_thread_id=TELEGRAM_TOPIC[topic_name] if topic_name else TELEGRAM_TOPIC[PROJECT_NAME],
      parse_mode='MarkdownV2',
    )


def send_telegram_error(trace: str, endpoint: bool = True):
  if IS_DEV or not TELEGRAM_TOKEN:
    return

  message = f'*Errore:*\n```\n{trace}\n```'
  if endpoint:
    message += f'\n\n*Request Data:*\n```json\n{extract_request_data()}\n```'

  run_async_safe(send_message(message))


def run_async_safe(coro):
  future = asyncio.run_coroutine_threadsafe(coro, loop)

  def callback(fut):
    exc = fut.exception()
    if exc:
      print('❌ Errore Telegram:', exc)  # noqa: T201
      try:
        with open('telegram_errors.log', 'a', encoding='utf-8') as f:
          import datetime

          f.write(f'{datetime.datetime.now().isoformat()} - Error: {exc}\n')
      except Exception:
        pass
    else:
      print('✅ Messaggio Telegram inviato con successo')  # noqa: T201

  future.add_done_callback(callback)


def send_telegram_message(text, topic_name=None):
  run_async_safe(send_message(text, topic_name=topic_name))


def extract_request_data(string_result: bool = True):
  request_info = {'path': request.path, 'method': request.method, 'headers': dict(request.headers)}
  args = request.args.to_dict()
  if args:
    request_info['args'] = args
  form = request.form.to_dict()
  if form:
    request_info['form'] = form
  json_data = request.get_json(silent=True)
  if json_data is not None:
    request_info['json'] = json_data
  return json.dumps(request_info, indent=2, ensure_ascii=False) if string_result else request_info


def split_message(text: str) -> list[str]:
  if len(text) <= MAX_MESSAGE_LENGTH:
    return [text]

  chunks = []
  while text:
    if len(text) <= MAX_MESSAGE_LENGTH:
      chunks.append(text)
      break

    split_at = text.rfind('\n', 0, MAX_MESSAGE_LENGTH)
    if split_at <= 0:
      split_at = MAX_MESSAGE_LENGTH

    segment = text[:split_at]
    if segment.count('```') % 2 == 1:
      block_start = segment.rfind('```')
      split_at = text.rfind('\n', 0, block_start)
      if split_at <= 0:
        split_at = block_start

    chunks.append(text[:split_at])
    text = text[split_at:].lstrip('\n')

  return chunks
