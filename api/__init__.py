from flask import g, request

from .settings import SWAGGER_KEY
from .hooks import register_flask_hooks


__all__ = ['register_flask_hooks', 'swagger_decorator', 'PrefixMiddleware']


def swagger_decorator(func):
  def wrapper(*args, **kwargs):
    if not SWAGGER_KEY:
      return {'status': 'ko', 'message': 'Errore autenticazione'}

    if 'SwaggerAuthorization' not in request.headers or request.headers['SwaggerAuthorization'] != SWAGGER_KEY:
      return {'status': 'ko', 'message': 'Autorizzazione negata'}

    g.log_swagger = True
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
