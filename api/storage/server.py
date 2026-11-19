import os
import shutil
import tempfile
import subprocess

from .utils import set_backup_env
from ..settings import BACKUP_SSH_CONFIG, BACKUP_FOLDER, SERVER_NAME, BACKUP_DAYS


def storage_decorator(func):
  def wrapper(*args, **kwargs):
    if not BACKUP_SSH_CONFIG:
      raise ValueError('BACKUP_SSH_CONFIG non configurato')

    return func(*args, **kwargs)

  wrapper.__name__ = func.__name__
  return wrapper


@storage_decorator
def _upload_file_server(content, full_path):
  subprocess.run(
    [
      'ssh',
      f'{BACKUP_SSH_CONFIG}',
      f'mkdir -p "{os.path.dirname(full_path)}"',
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
        f'{BACKUP_SSH_CONFIG}:{full_path}',
      ],
      check=True,
      capture_output=True,
      text=True,
    )

  finally:
    if tmp_path and os.path.exists(tmp_path):
      os.remove(tmp_path)

  return full_path


@storage_decorator
def _delete_file_server(full_path):
  subprocess.run(
    [
      'ssh',
      f'{BACKUP_SSH_CONFIG}',
      f'rm "{full_path}"',
    ],
    check=True,
    capture_output=True,
    text=True,
  )


@storage_decorator
def _list_files_server(full_path):
  return [
    os.path.join(full_path, file)
    for file in subprocess.run(
      [
        'ssh',
        f'{BACKUP_SSH_CONFIG}',
        f'find "{full_path}" -maxdepth 1 -type f -printf "%f\\n"',
      ],
      capture_output=True,
      text=True,
      check=True,
    )
    .stdout.strip()
    .splitlines()
  ]


@storage_decorator
def _unlock_folder_backup_server():
  subprocess.run(
    [
      'restic',
      '-r',
      f'sftp:{BACKUP_SSH_CONFIG}:{os.path.join(BACKUP_FOLDER, "folder-backup")}',
      'unlock',
      '--remove-all',
    ],
    env=set_backup_env(),
    capture_output=True,
    text=True,
  )


@storage_decorator
def _folder_backup_server(folder_to_backup):
  _unlock_folder_backup_server()
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


@storage_decorator
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


@storage_decorator
def _prepare_db_dump_repository_server(repository):
  if (
    subprocess.run(
      ['restic', '-r', f'sftp:{BACKUP_SSH_CONFIG}:{repository}', 'cat', 'config'],
      env=set_backup_env(),
      capture_output=True,
      text=True,
    ).returncode
    != 0
  ):
    subprocess.run(
      ['restic', '-r', f'sftp:{BACKUP_SSH_CONFIG}:{repository}', 'init'],
      env=set_backup_env(),
      check=True,
      capture_output=True,
      text=True,
    )

  subprocess.run(
    ['restic', '-r', f'sftp:{BACKUP_SSH_CONFIG}:{repository}', 'unlock', '--remove-all'],
    env=set_backup_env(),
    capture_output=True,
    text=True,
  )


@storage_decorator
def _upload_db_dump_server(file_path, repository, filename):
  _prepare_db_dump_repository_server(repository)
  with open(file_path, 'rb') as content:
    subprocess.run(
      [
        'restic',
        '-r',
        f'sftp:{BACKUP_SSH_CONFIG}:{repository}',
        'backup',
        '--stdin',
        '--stdin-filename',
        filename,
        '--host',
        SERVER_NAME,
      ],
      stdin=content,
      env=set_backup_env(),
      check=True,
      capture_output=True,
      text=True,
    )
  return repository


@storage_decorator
def _cleanup_db_dumps_server(repository):
  subprocess.run(
    [
      'restic',
      '-r',
      f'sftp:{BACKUP_SSH_CONFIG}:{repository}',
      'forget',
      '--keep-within',
      f'{BACKUP_DAYS}d',
      '--prune',
    ],
    env=set_backup_env(),
    check=True,
    capture_output=True,
    text=True,
  )


@storage_decorator
def _download_db_dump_server(repository, filename, output_path, snapshot):
  with open(output_path, 'wb') as output:
    subprocess.run(
      ['restic', '-r', f'sftp:{BACKUP_SSH_CONFIG}:{repository}', 'dump', snapshot, f'/{filename}'],
      stdout=output,
      env=set_backup_env(),
      check=True,
    )
  return output_path
