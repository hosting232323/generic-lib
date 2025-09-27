import os
import traceback
from flask import jsonify, request

from database_api import Session
from database_api.backup import db_backup


def error_catching_decorator(func):

  def wrapper(*args, **kwargs):
    try:
      return func(*args, **kwargs)
    except Exception:
      traceback.print_exc()
      return jsonify({
        'status': 'ko',
        'message': 'Errore generico'
      })

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


def internal_backup(db_name):
  with Session() as session:
    db_backup(session.get_bind(), db_name)
    return 'Backup eseguito', 200
