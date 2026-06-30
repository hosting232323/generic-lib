"""
Manage restricted user backup access.
Provides functions for restricted users to list and download their backups.
"""

import os
import subprocess
from pathlib import Path

from .server import storage_decorator, get_full_path, set_backup_env
from ..settings import BACKUP_SSH_CONFIG, BACKUP_FOLDER


@storage_decorator
def list_user_backups(username: str, subfolder: str = None) -> list:
  """
  List all backup files for a restricted user.

  Args:
    username: The restricted user's username
    subfolder: Optional subfolder within the user's backup directory

  Returns:
    List of backup file paths
  """
  if not BACKUP_SSH_CONFIG:
    raise ValueError('BACKUP_SSH_CONFIG non configurato')

  # Build path: /backup/users/{username}/backup/{subfolder}
  user_backup_path = os.path.join(BACKUP_FOLDER, 'users', username, 'backup')
  if subfolder:
    user_backup_path = os.path.join(user_backup_path, subfolder)

  try:
    result = subprocess.run(
      [
        'ssh',
        BACKUP_SSH_CONFIG,
        f'find "{user_backup_path}" -maxdepth 1 -type f -printf "%f\\n" 2>/dev/null || echo ""',
      ],
      capture_output=True,
      text=True,
      timeout=10,
    )

    if result.returncode != 0:
      return []

    files = [
      os.path.join(user_backup_path, filename)
      for filename in result.stdout.strip().splitlines()
      if filename
    ]
    return sorted(files)

  except subprocess.TimeoutExpired:
    raise RuntimeError(f'Timeout listing backups for user {username}')


@storage_decorator
def get_user_backup_file(username: str, filename: str) -> bytes:
  """
  Download a single backup file for a restricted user.

  Args:
    username: The restricted user's username
    filename: The backup file to download (must not contain path separators)

  Returns:
    File content as bytes
  """
  if not BACKUP_SSH_CONFIG:
    raise ValueError('BACKUP_SSH_CONFIG non configurato')

  # Security: prevent directory traversal
  if '/' in filename or '\\' in filename or '..' in filename:
    raise ValueError('Invalid filename: path separators not allowed')

  user_backup_path = os.path.join(BACKUP_FOLDER, 'users', username, 'backup', filename)

  try:
    result = subprocess.run(
      [
        'ssh',
        BACKUP_SSH_CONFIG,
        f'cat "{user_backup_path}" 2>/dev/null',
      ],
      capture_output=True,
      timeout=300,  # 5 minute timeout for large files
    )

    if result.returncode != 0:
      raise FileNotFoundError(f'Backup file not found: {filename}')

    return result.stdout

  except subprocess.TimeoutExpired:
    raise RuntimeError(f'Timeout downloading backup {filename}')


@storage_decorator
def get_user_backup_file_size(username: str, filename: str) -> int:
  """
  Get the size of a backup file without downloading it.

  Args:
    username: The restricted user's username
    filename: The backup file (must not contain path separators)

  Returns:
    File size in bytes
  """
  if not BACKUP_SSH_CONFIG:
    raise ValueError('BACKUP_SSH_CONFIG non configurato')

  if '/' in filename or '\\' in filename or '..' in filename:
    raise ValueError('Invalid filename: path separators not allowed')

  user_backup_path = os.path.join(BACKUP_FOLDER, 'users', username, 'backup', filename)

  try:
    result = subprocess.run(
      [
        'ssh',
        BACKUP_SSH_CONFIG,
        f'stat -c "%s" "{user_backup_path}" 2>/dev/null || echo "0"',
      ],
      capture_output=True,
      text=True,
      timeout=10,
    )

    if result.returncode != 0:
      return 0

    return int(result.stdout.strip() or '0')

  except (subprocess.TimeoutExpired, ValueError):
    return 0


@storage_decorator
def get_user_backup_info(username: str) -> dict:
  """
  Get aggregate info about a user's backups.

  Args:
    username: The restricted user's username

  Returns:
    Dict with 'total_files', 'total_size', 'files' keys
  """
  files = list_user_backups(username)
  total_size = 0
  file_info = []

  for file_path in files:
    filename = os.path.basename(file_path)
    size = get_user_backup_file_size(username, filename)
    total_size += size
    file_info.append({
      'filename': filename,
      'path': file_path,
      'size': size,
      'size_mb': round(size / (1024 * 1024), 2),
    })

  return {
    'username': username,
    'total_files': len(file_info),
    'total_size': total_size,
    'total_size_mb': round(total_size / (1024 * 1024), 2),
    'files': file_info,
  }
