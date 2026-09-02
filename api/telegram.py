import sys
import json
import asyncio
import threading
import telegramify_markdown
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
  'addlance': 4294970503,
}
MAX_MESSAGE_LENGTH = 4096
MAX_TELEGRAM_TEXT = 5 * MAX_MESSAGE_LENGTH
CHUNK_HEADER_RESERVE = 64
TRUNCATED_SUFFIX = '\n… messaggio troncato'
REDACTED_VALUE = '[REDACTED]'
SENSITIVE_REQUEST_KEYS = {
  'access_token',
  'api_key',
  'authorization',
  'client_secret',
  'cookie',
  'id_token',
  'password',
  'proxy_authorization',
  'refresh_token',
  'secret',
  'set_cookie',
  'swagger_authorization',
  'token',
  'x_api_key',
  'x_auth_token',
}
_TELEGRAM_SEND_LOCK = threading.Lock()


async def _render_chunks(text, max_utf16_len=MAX_MESSAGE_LENGTH):
  chunks = []
  boxes = await telegramify_markdown.telegramify(text, min_file_lines=sys.maxsize, render_mermaid=False)
  for box in boxes:
    if box.content_type != telegramify_markdown.ContentTypes.TEXT:
      continue
    chunks.extend(telegramify_markdown.split_markdownv2(box.text, box.entities, max_utf16_len=max_utf16_len))
  return chunks


async def _send_chunks(bot, text, topic_id, title=None):
  max_chunk_length = MAX_MESSAGE_LENGTH - CHUNK_HEADER_RESERVE if title else MAX_MESSAGE_LENGTH
  chunks = await _render_chunks(text, max_utf16_len=max_chunk_length)
  total = len(chunks)

  for index, chunk in enumerate(chunks, start=1):
    header = ''
    if title:
      part = f' {index}/{total}' if total > 1 else ''
      header = f'*{title}{part}:*\n'
    await bot.send_message(
      chat_id=CHAT_ID,
      text=header + chunk,
      message_thread_id=topic_id,
      parse_mode='MarkdownV2',
    )


async def send_message(text, topic_name=None):
  topic_id = TELEGRAM_TOPIC.get(topic_name or PROJECT_NAME, TELEGRAM_TOPIC['default'])
  await _send_chunks(Bot(TELEGRAM_TOKEN), text, topic_id)


async def send_error_message(trace, request_data=None):
  topic_id = TELEGRAM_TOPIC.get(PROJECT_NAME, TELEGRAM_TOPIC['default'])
  bot = Bot(TELEGRAM_TOKEN)

  await _send_chunks(bot, f'```\n{trace}\n```', topic_id, title='Errore')
  if request_data is not None:
    await _send_chunks(bot, f'```json\n{request_data}\n```', topic_id, title='Request Data')


def _truncate_text(text):
  if len(text) <= MAX_TELEGRAM_TEXT:
    return text
  return text[:MAX_TELEGRAM_TEXT] + TRUNCATED_SUFFIX


def _send_in_background(coroutine_factory):
  def run():
    try:
      with _TELEGRAM_SEND_LOCK:
        asyncio.run(coroutine_factory())
      print('✅ Messaggio Telegram inviato con successo')  # noqa: T201
    except Exception as exc:
      print('❌ Errore Telegram:', exc)  # noqa: T201
      try:
        with open('telegram_errors.log', 'a', encoding='utf-8') as f:
          import datetime

          f.write(f'{datetime.datetime.now().isoformat()} - Error: {exc}\n')
      except Exception:
        pass

  threading.Thread(target=run, daemon=True).start()


def send_telegram_error(trace: str, endpoint: bool = True):
  if IS_DEV or not TELEGRAM_TOKEN:
    return

  request_data = _truncate_text(extract_request_data()) if endpoint else None
  trace = _truncate_text(trace)
  _send_in_background(lambda: send_error_message(trace, request_data))


def send_telegram_message(text, topic_name=None):
  text = _truncate_text(text)
  _send_in_background(lambda: send_message(text, topic_name=topic_name))


def _normalize_request_key(key):
  return str(key).strip().lower().replace('-', '_')


def _redact_sensitive_data(value):
  if isinstance(value, dict):
    return {
      key: REDACTED_VALUE if _normalize_request_key(key) in SENSITIVE_REQUEST_KEYS else _redact_sensitive_data(item)
      for key, item in value.items()
    }
  if isinstance(value, list):
    return [_redact_sensitive_data(item) for item in value]
  return value


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
  request_info = _redact_sensitive_data(request_info)
  return json.dumps(request_info, indent=2, ensure_ascii=False) if string_result else request_info
