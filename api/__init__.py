import os
import traceback
from flask import request
import requests
from telegram import Bot

IS_DEV = int(os.environ.get('IS_DEV', 1)) == 1
bot = Bot(os.environ['TELEGRAM_TOKEN'])
CHAT_ID = -1003410500390
topic = {
  "default": 4294967297,
  "wooffy-be": 4294967352,
  "italco-be": 4294967355,
  "chatty-be": 4294967354,
  "generic-be": 4294967350,
  "strongbox-be": 4294967353,
  "generic-booking": 4294967351
}
thread_id = topic[os.environ.get("PROJECT_NAME", 'default')]

def error_catching_decorator(func):
  def wrapper(*args, **kwargs):
    try:
      return func(*args, **kwargs)
    except Exception:
      error_trace = traceback.format_exc()
      print(error_trace)
      if not IS_DEV:
        bot.send_message(
          chat_id=CHAT_ID,
          text=error_trace,
          message_thread_id=thread_id,
          parse_mode="Markdown"
        )

      requests.post(f'{os.environ["TELEGRAM_ALERT"]}/alert', json={'topic': os.environ["PROJECT_NAME"], 'trace': error_trace})
      return {'status': 'ko', 'message': 'Errore generico'}

  wrapper.__name__ = func.__name__
  return wrapper


def swagger_decorator(func):
  def wrapper(*args, **kwargs):
    if (
      'SwaggerAuthorization' not in request.headers
      or request.headers['SwaggerAuthorization'] != os.environ['SWAGGER_KEY']
    ):
      return {'status': 'ko', 'message': 'Autorizzazione negata'}

    return func(*args, **kwargs)

  wrapper.__name__ = func.__name__
  return wrapper


class PrefixMiddleware:
  def __init__(self, app, prefix=''):
    self.app = app
    self.prefix = prefix

  def __call__(self, environ, start_response):
    if environ['PATH_INFO'].startswith(self.prefix):
      environ['PATH_INFO'] = environ['PATH_INFO'][len(self.prefix) :]
      environ['SCRIPT_NAME'] = self.prefix
      return self.app(environ, start_response)
    else:
      start_response('404', [('Content-Type', 'text/plain')])
      return [b'Not Found']
