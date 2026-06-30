"""
API endpoints for managing restricted user backups.
Provides read-only access for users to view and download their backups.
"""

from flask import Blueprint, jsonify, send_file, abort
from functools import wraps
from io import BytesIO

from api.storage.restricted_users import (
  list_user_backups,
  get_user_backup_file,
  get_user_backup_info,
)

restricted_backups_bp = Blueprint('restricted_backups', __name__, url_prefix='/api/restricted-backups')


def require_username(f):
  """Decorator to ensure username is provided in query params."""
  @wraps(f)
  def decorated_function(*args, **kwargs):
    from flask import request
    username = request.args.get('username')
    if not username:
      return jsonify({'error': 'username parameter is required'}), 400
    # In a real app, verify the user is authenticated and can access this username
    return f(username=username, *args, **kwargs)
  return decorated_function


@restricted_backups_bp.route('/list', methods=['GET'])
@require_username
def list_backups(username):
  """
  List all backup files for a user.
  Query params:
    - username: The username to list backups for
    - subfolder: (optional) Subfolder within user's backup directory
  """
  try:
    from flask import request
    subfolder = request.args.get('subfolder')
    files = list_user_backups(username, subfolder)
    return jsonify({
      'username': username,
      'files': files,
      'count': len(files),
    })
  except ValueError as e:
    return jsonify({'error': str(e)}), 400
  except Exception as e:
    return jsonify({'error': f'Failed to list backups: {str(e)}'}), 500


@restricted_backups_bp.route('/info', methods=['GET'])
@require_username
def get_info(username):
  """
  Get detailed info about a user's backups.
  Query params:
    - username: The username to get info for
  """
  try:
    info = get_user_backup_info(username)
    return jsonify(info)
  except ValueError as e:
    return jsonify({'error': str(e)}), 400
  except Exception as e:
    return jsonify({'error': f'Failed to get backup info: {str(e)}'}), 500


@restricted_backups_bp.route('/download', methods=['GET'])
@require_username
def download_backup(username):
  """
  Download a backup file.
  Query params:
    - username: The username
    - filename: The backup file to download
  """
  try:
    from flask import request
    filename = request.args.get('filename')
    if not filename:
      return jsonify({'error': 'filename parameter is required'}), 400

    file_content = get_user_backup_file(username, filename)
    return send_file(
      BytesIO(file_content),
      download_name=filename,
      as_attachment=True,
      mimetype='application/octet-stream',
    )
  except FileNotFoundError:
    return jsonify({'error': f'Backup file not found: {filename}'}), 404
  except ValueError as e:
    return jsonify({'error': str(e)}), 400
  except Exception as e:
    return jsonify({'error': f'Failed to download backup: {str(e)}'}), 500


def init_restricted_backups_api(app):
  """Initialize restricted backups API endpoints with Flask app."""
  app.register_blueprint(restricted_backups_bp)
