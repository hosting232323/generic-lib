import os
import subprocess

from .utils import set_backup_env
from ..settings import BACKUP_FOLDER, SERVER_NAME, BACKUP_DAYS


def _upload_file_local(content, full_path):
  os.makedirs(os.path.dirname(full_path), exist_ok=True)

  with open(full_path, 'wb') as file:
    file.write(content.read())
  return full_path


def _delete_file_local(full_path):
  os.remove(full_path)


def _list_files_local(full_path):
  return [
    os.path.join(full_path, file) for file in os.listdir(full_path) if os.path.isfile(os.path.join(full_path, file))
  ]


def _unlock_folder_backup_local():
  subprocess.run(
    [
      'restic',
      '-r',
      os.path.join(BACKUP_FOLDER, 'folder-backup'),
      'unlock',
      '--remove-all',
    ],
    env=set_backup_env(),
    capture_output=True,
    text=True,
  )


def _folder_backup_local(folder_to_backup):
  _unlock_folder_backup_local()
  subprocess.run(
    [
      'restic',
      '-r',
      os.path.join(BACKUP_FOLDER, 'folder-backup'),
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


def _cleanup_folder_backups_local():
  subprocess.run(
    [
      'restic',
      '-r',
      os.path.join(BACKUP_FOLDER, 'folder-backup'),
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


def _prepare_db_dump_repository_local(repository):
  if (
    subprocess.run(
      ['restic', '-r', repository, 'cat', 'config'],
      env=set_backup_env(),
      capture_output=True,
      text=True,
    ).returncode
    != 0
  ):
    subprocess.run(
      ['restic', '-r', repository, 'init'],
      env=set_backup_env(),
      check=True,
      capture_output=True,
      text=True,
    )

  subprocess.run(
    ['restic', '-r', repository, 'unlock', '--remove-all'],
    env=set_backup_env(),
    capture_output=True,
    text=True,
  )


def _upload_db_dump_local(file_path, repository, filename):
  _prepare_db_dump_repository_local(repository)
  with open(file_path, 'rb') as content:
    subprocess.run(
      [
        'restic',
        '-r',
        repository,
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


def _cleanup_db_dumps_local(repository):
  subprocess.run(
    [
      'restic',
      '-r',
      repository,
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


def _download_db_dump_local(repository, filename, output_path, snapshot):
  with open(output_path, 'wb') as output:
    subprocess.run(
      ['restic', '-r', repository, 'dump', snapshot, f'/{filename}'],
      stdout=output,
      env=set_backup_env(),
      check=True,
    )
  return output_path
