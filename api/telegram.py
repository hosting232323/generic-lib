import os
import asyncio
import threading
import json
from telegram import Bot
from flask import request


CHAT_ID = -1003410500390
TELEGRAM_TOPIC = {
  'default': 4294967297,
  'wooffy-be': 4294967352,
  'italco-be': 4294967355,
  'chatty-be': 4294967354,
  'generic-be': 4294967350,
  'strongbox-be': 4294967353,
  'generic-booking': 4294967351,
}

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)


def start_loop(loop):
  asyncio.set_event_loop(loop)
  loop.run_forever()


threading.Thread(target=start_loop, args=(loop,), daemon=True).start()

def escape_md(text: str) -> str:
  escape_chars = r'_*\[\]()~`>#+-=|{}.!'
  for ch in escape_chars:
    text = text.replace(ch, f"\\{ch}")
  return text


async def send_error(text):
  await Bot(os.environ['TELEGRAM_TOKEN']).send_message(
    chat_id=CHAT_ID, 
    text=text, 
    message_thread_id=TELEGRAM_TOPIC[os.environ.get('PROJECT_NAME', 'default')],
    parse_mode="MarkdownV2"
  )


def send_telegram_error(trace: str, include_request: bool = False):
  if int(os.environ.get('IS_DEV', 1)) == 1:
    return

  message = f"*Errore:*\n```\n{trace}\n```"
  if include_request:
    req_json = extract_request_data()
    escaped_req = escape_md(req_json)

    message += f"\n\n*Request Data:*\n```\n{escaped_req}\n```"

  asyncio.run_coroutine_threadsafe(send_error(message), loop)


def extract_request_data():
  request_info = {
    'path': request.path,
    'method': request.method
  }

  args = request.args.to_dict()
  if args:
    request_info['args'] = args

  form = request.form.to_dict()
  if form:
    request_info['form'] = form

  json_data = request.get_json(silent=True)
  if json_data is not None:
    request_info['json'] = json_data

  request_info['headers'] = dict(request.headers)

  return json.dumps(request_info, indent=2, ensure_ascii=False)
