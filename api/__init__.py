from flask import g, request

from . import hooks
from .settings import SWAGGER_KEY


def register_flask_hooks(
  app, log_folder=None, excluded_paths=hooks.EXCLUDED_PATHS, excluded_prefixes=hooks.EXCLUDED_PREFIXES
):
  @app.errorhandler(Exception)
  def handle_exception(error):
    return hooks.handle_exception(error)

  if log_folder:

    @app.after_request
    def log_request(response):
      return hooks.log_request(response, log_folder, excluded_paths, excluded_prefixes)

  return app


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
