from functools import wraps
import os
import shlex
import shutil
import tempfile
import subprocess

from .utils import set_backup_env
from ..settings import BACKUP_SSH_CONFIG, BACKUP_FOLDER, SERVER_NAME, BACKUP_DAYS


def _requires_server_config(func):
  @wraps(func)
  def wrapper(*args, **kwargs):
    if not BACKUP_SSH_CONFIG:
      raise ValueError('BACKUP_SSH_CONFIG non configurato')

    return func(*args, **kwargs)

  return wrapper


@_requires_server_config
def _upload_file_server(content, full_path):
  subprocess.run(
    [
      'ssh',
      f'{BACKUP_SSH_CONFIG}',
      f'mkdir -p -- {shlex.quote(os.path.dirname(full_path))}',
    ],
    check=True,
    capture_output=True,
    text=True,
  )

  tmp_path = None
  try:
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
      shutil.copyfileobj(content, tmp)
      tmp_path = tmp.name

    subprocess.run(
      [
        'rsync',
        '-avz',
        '--partial',
        '--append-verify',
        tmp_path,
        f'{BACKUP_SSH_CONFIG}:{shlex.quote(full_path)}',
      ],
      check=True,
      capture_output=True,
      text=True,
    )

  finally:
    if tmp_path and os.path.exists(tmp_path):
      os.remove(tmp_path)

  return full_path


@_requires_server_config
def _delete_file_server(full_path):
  subprocess.run(
    [
      'ssh',
      f'{BACKUP_SSH_CONFIG}',
      f'rm -- {shlex.quote(full_path)}',
    ],
    check=True,
    capture_output=True,
    text=True,
  )


@_requires_server_config
def _list_files_server(full_path):
  quoted_path = shlex.quote(full_path)
  return sorted(
    [
      os.path.join(full_path, file)
      for file in subprocess.run(
        [
          'ssh',
          f'{BACKUP_SSH_CONFIG}',
          f'if [ -d {quoted_path} ]; then find {quoted_path} -maxdepth 1 -type f -printf "%f\\n"; fi',
        ],
        capture_output=True,
        text=True,
        check=True,
      )
      .stdout.strip()
      .splitlines()
    ]
  )


@_requires_server_config
def _folder_backup_server(folder_to_backup):
  subprocess.run(
    [
      'restic',
      '-r',
      f'sftp:{BACKUP_SSH_CONFIG}:{os.path.join(BACKUP_FOLDER, "folder-backup")}',
      'backup',
      folder_to_backup,
      '--host',
      SERVER_NAME,
    ],
    env=set_backup_env(),
    check=True,
    capture_output=True,
    text=True,
  )


@_requires_server_config
def _cleanup_folder_backups_server():
  subprocess.run(
    [
      'restic',
      '-r',
      f'sftp:{BACKUP_SSH_CONFIG}:{os.path.join(BACKUP_FOLDER, "folder-backup")}',
      'forget',
      '--keep-daily',
      str(BACKUP_DAYS),
      '--prune',
    ],
    env=set_backup_env(),
    check=True,
    capture_output=True,
    text=True,
  )
