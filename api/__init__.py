import os
import traceback
from flask import request
import requests


def error_catching_decorator(func):
  def wrapper(*args, **kwargs):
    try:
      return func(*args, **kwargs)
    except Exception:
      error_trace = traceback.format_exc()
      print(error_trace)
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
