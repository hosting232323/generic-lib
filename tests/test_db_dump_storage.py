"""Test dei comandi restic che salvano, puliscono ed estraggono i dump del database.

restic qui non c'e': subprocess.run e' sostituito da un finto che registra i
comandi e risponde come il binario vero. Si controlla che i dump passino da
stdin (il file non viene copiato nel repository col suo path), che il
repository si crei solo quando manca, e che la password arrivi da ambiente e
mai sulla riga di comando.
"""

import subprocess
from types import SimpleNamespace

import pytest

from api.storage import local as local_module
from api.storage import server as server_module
from api.storage import utils as utils_module
from api.storage import cleanup_db_dumps, download_db_dump, upload_db_dump


SSH = 'backup@macchina-di-backup'


@pytest.fixture(autouse=True)
def backup_settings(monkeypatch):
  monkeypatch.setattr(utils_module, 'RESTIC_PASSWORD', 'restic-segreta')
  monkeypatch.setattr(utils_module, 'BACKUP_FOLDER', '/srv/backup/italco')
  monkeypatch.setattr(utils_module, 'SERVER_NAME', 'combusken')
  monkeypatch.setattr(local_module, 'SERVER_NAME', 'combusken')
  monkeypatch.setattr(server_module, 'SERVER_NAME', 'combusken')
  monkeypatch.setattr(local_module, 'BACKUP_DAYS', 20)
  monkeypatch.setattr(server_module, 'BACKUP_DAYS', 20)
  monkeypatch.setattr(server_module, 'BACKUP_SSH_CONFIG', SSH)


def _fake_restic(monkeypatch, repository_exists=True):
  calls = []

  def run(command, **kwargs):
    stdin = kwargs.pop('stdin', None)
    calls.append(SimpleNamespace(command=command, stdin=stdin.read() if stdin else None, **kwargs))

    if command[3:] == ['cat', 'config'] and not repository_exists:
      return SimpleNamespace(returncode=10, stdout='', stderr='Fatal: repository does not exist')
    if 'dump' in command:
      kwargs['stdout'].write(b'dump-dal-repository')
    return SimpleNamespace(returncode=0, stdout='', stderr='')

  monkeypatch.setattr(local_module.subprocess, 'run', run)
  return calls


def _commands(calls):
  return [call.command[3:] for call in calls]


def test_the_dump_goes_through_stdin_with_a_fixed_name(monkeypatch, tmp_path):
  dump = tmp_path / '261118030000.dump'
  dump.write_bytes(b'contenuto-del-dump')
  calls = _fake_restic(monkeypatch)

  upload_db_dump(str(dump), '/srv/backup/italco/db-backup', 'database.dump')

  backup = calls[-1]
  assert backup.command == [
    'restic',
    '-r',
    '/srv/backup/italco/db-backup',
    'backup',
    '--stdin',
    '--stdin-filename',
    'database.dump',
    '--host',
    'combusken',
  ]
  assert backup.stdin == b'contenuto-del-dump'
  assert backup.check is True


def test_the_password_travels_in_the_environment_not_in_the_command(monkeypatch, tmp_path):
  dump = tmp_path / 'db.dump'
  dump.write_bytes(b'x')
  calls = _fake_restic(monkeypatch)

  upload_db_dump(str(dump), '/srv/backup/italco/db-backup', 'database.dump')

  for call in calls:
    assert call.env['RESTIC_PASSWORD'] == 'restic-segreta'
    assert 'restic-segreta' not in ' '.join(call.command)


def test_an_existing_repository_is_not_initialized_again(monkeypatch, tmp_path):
  dump = tmp_path / 'db.dump'
  dump.write_bytes(b'x')
  calls = _fake_restic(monkeypatch)

  upload_db_dump(str(dump), '/srv/backup/italco/db-backup', 'database.dump')

  assert ['init'] not in _commands(calls)
  assert _commands(calls)[:2] == [['cat', 'config'], ['unlock', '--remove-all']]


def test_the_first_backup_creates_the_repository(monkeypatch, tmp_path):
  dump = tmp_path / 'db.dump'
  dump.write_bytes(b'x')
  calls = _fake_restic(monkeypatch, repository_exists=False)

  upload_db_dump(str(dump), '/srv/backup/italco/db-backup', 'database.dump')

  assert _commands(calls)[:3] == [['cat', 'config'], ['init'], ['unlock', '--remove-all']]


def test_a_failed_backup_raises(monkeypatch, tmp_path):
  """db_backup ripiega solo se l'upload solleva: un errore restic non va perso."""
  dump = tmp_path / 'db.dump'
  dump.write_bytes(b'x')

  def run(command, **kwargs):
    if 'backup' in command and kwargs.get('check'):
      raise subprocess.CalledProcessError(1, command, stderr='Fatal: no space left on device')
    return SimpleNamespace(returncode=0, stdout='', stderr='')

  monkeypatch.setattr(local_module.subprocess, 'run', run)

  with pytest.raises(subprocess.CalledProcessError):
    upload_db_dump(str(dump), '/srv/backup/italco/db-backup', 'database.dump', server=True)


def test_on_the_backup_server_the_repository_is_reached_via_sftp(monkeypatch, tmp_path):
  dump = tmp_path / 'db.dump'
  dump.write_bytes(b'x')
  calls = _fake_restic(monkeypatch)

  assert upload_db_dump(str(dump), '/srv/backup/italco/db-backup', 'database.dump', server=True)

  assert {call.command[2] for call in calls} == {f'sftp:{SSH}:/srv/backup/italco/db-backup'}


def test_without_ssh_config_the_server_mode_refuses(monkeypatch, tmp_path):
  monkeypatch.setattr(server_module, 'BACKUP_SSH_CONFIG', None)
  calls = _fake_restic(monkeypatch)

  with pytest.raises(ValueError, match='BACKUP_SSH_CONFIG'):
    upload_db_dump(str(tmp_path / 'db.dump'), '/srv/backup/italco/db-backup', 'database.dump', server=True)

  assert calls == []


@pytest.mark.parametrize('server, repository', [(None, '/r/db-backup'), (True, f'sftp:{SSH}:/r/db-backup')])
def test_cleanup_keeps_the_last_backup_days(monkeypatch, server, repository):
  calls = _fake_restic(monkeypatch)

  cleanup_db_dumps('/r/db-backup', server)

  assert [call.command for call in calls] == [
    ['restic', '-r', repository, 'forget', '--keep-within', '20d', '--prune'],
  ]
  assert calls[0].check is True


@pytest.mark.parametrize('server, repository', [(None, '/r/db-backup'), (True, f'sftp:{SSH}:/r/db-backup')])
def test_download_writes_the_dump_of_the_snapshot(monkeypatch, tmp_path, server, repository):
  calls = _fake_restic(monkeypatch)
  output = tmp_path / 'restore.dump'

  assert download_db_dump('/r/db-backup', 'database.dump', str(output), 'a1b2c3d4', server) == str(output)

  assert calls[0].command == ['restic', '-r', repository, 'dump', 'a1b2c3d4', '/database.dump']
  assert output.read_bytes() == b'dump-dal-repository'
