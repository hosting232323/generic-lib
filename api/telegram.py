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
}


async def send_message(text, topic_name=None):
  # min_file_lines=sys.maxsize: i blocchi di codice restano inline invece di diventare allegati
  boxes = await telegramify_markdown.telegramify(text, min_file_lines=sys.maxsize, render_mermaid=False)
  for box in boxes:
    if box.content_type != telegramify_markdown.ContentTypes.TEXT:
      continue
    for chunk in telegramify_markdown.split_markdownv2(box.text, box.entities):
      await Bot(TELEGRAM_TOKEN).send_message(
        chat_id=CHAT_ID,
        text=chunk,
        message_thread_id=TELEGRAM_TOPIC[topic_name] if topic_name else TELEGRAM_TOPIC[PROJECT_NAME],
        parse_mode='MarkdownV2',
      )


def send_telegram_error(trace: str, endpoint: bool = True):
  if IS_DEV or not TELEGRAM_TOKEN:
    return

  message = f'**Errore:**\n```\n{trace}\n```'
  if endpoint:
    message += f'\n\n**Request Data:**\n```json\n{extract_request_data()}\n```'

  send_telegram_message(message)


def send_telegram_message(text, topic_name=None):
  def run():
    try:
      asyncio.run(send_message(text, topic_name=topic_name))
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
