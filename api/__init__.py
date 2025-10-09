import os
import traceback
from flask import request


def error_catching_decorator(func):

  def wrapper(*args, **kwargs):
    try:
      return func(*args, **kwargs)
    except Exception:
      traceback.print_exc()
      return {
        'status': 'ko',
        'message': 'Errore generico'
      }

  wrapper.__name__ = func.__name__
  return wrapper


def swagger_decorator(func):

  def wrapper(*args, **kwargs):
    if not 'SwaggerAuthorization' in request.headers or request.headers['SwaggerAuthorization'] != os.environ['SWAGGER_KEY']:
      return {
        'status': 'ko',
        'message': 'Autorizzazione negata'
      }

    return func(*args, **kwargs)

  wrapper.__name__ = func.__name__
  return wrapper
