"""Test della retention e del fallback locale dei dump del database.

## Retention

La regola e' una sola: si cancella un dump quando ha piu' di BACKUP_DAYS
giorni. Il punto delicato e' da dove si ricava quell'eta'.

Non dal filesystem. Con `server=True` i path che arrivano dal listing sono
quelli della macchina di backup, raggiungibile solo via ssh: qualsiasi
os.path.getmtime() su quei path solleverebbe FileNotFoundError, e siccome
db_backup gira in un thread daemon che intercetta solo CalledProcessError,
l'errore sparirebbe senza notifica lasciando i dump ad accumularsi.

L'eta' si ricava quindi dal nome del file, che data_export genera come
`%y%m%d%H%M%S.dump`: e' l'unico dato disponibile in entrambe le modalita' e
non richiede di toccare il disco. Da qui i casi coperti:

- si cancella solo cio' che e' scaduto, e mai il resto;
- i path remoti (inesistenti in locale) funzionano come quelli locali;
- un nome fuori formato o senza estensione .dump si tiene, non si indovina.

## Fallback locale

Quando l'upload verso la destinazione finale non riesce (tipicamente disco
pieno) il dump appena prodotto e' l'unica copia esistente. Non va cancellato:
finisce in BACKUP_FALLBACK_FOLDER sul sistema operativo e la notifica Telegram
parte comunque, dicendo dove e' rimasto. Al primo backup riuscito i dump tenuti
da parte vengono ricaricati e rimossi dal fallback.
"""

import pytest
import subprocess
from datetime import datetime, timedelta

from api.settings import BACKUP_DAYS
from database_api import backup as backup_module
from database_api.backup import cleanup_old_backups, db_backup, flush_fallback_backups, parse_backup_date


def _dump_name(days_ago: float) -> str:
  return f'{(datetime.now() - timedelta(days=days_ago)).strftime("%y%m%d%H%M%S")}.dump'


def _collect_deletes(monkeypatch, listed_files):
  deleted = []
  monkeypatch.setattr(backup_module, 'get_all_filenames', lambda *args, **kwargs: listed_files)
  monkeypatch.setattr(backup_module, 'delete_file', lambda filename, *args, **kwargs: deleted.append(filename))
  return deleted


def test_parse_backup_date_reads_the_timestamp_in_the_name():
  assert parse_backup_date('/backup/prod/postgres-backup/240115103000.dump') == datetime(2024, 1, 15, 10, 30, 0)


def test_parse_backup_date_ignores_names_out_of_format():
  assert parse_backup_date('/backup/prod/postgres-backup/dump-di-prova.dump') is None
  assert parse_backup_date('/backup/prod/postgres-backup/240115103000.sql') is None
  assert parse_backup_date('/backup/prod/postgres-backup/240115103000') is None


def test_cleanup_deletes_only_expired_dumps(monkeypatch):
  expired = _dump_name(BACKUP_DAYS + 5)
  fresh = _dump_name(1)
  on_the_edge = _dump_name(BACKUP_DAYS - 0.5)

  folder = '/backup/prod/postgres-backup'
  deleted = _collect_deletes(monkeypatch, [f'{folder}/{expired}', f'{folder}/{fresh}', f'{folder}/{on_the_edge}'])

  cleanup_old_backups()

  assert deleted == [expired]


def test_cleanup_works_on_remote_paths_that_do_not_exist_locally(monkeypatch):
  """Regressione: la retention leggeva l'eta' dal filesystem locale.

  Questi path esistono solo sulla macchina di backup. Se il codice tornasse a
  interrogare il disco, qui otterrebbe FileNotFoundError invece di cancellare.
  """
  expired = _dump_name(BACKUP_DAYS + 1)
  remote_folder = '/srv/backup-che-non-esiste-qui/prod/postgres-backup'
  deleted = _collect_deletes(monkeypatch, [f'{remote_folder}/{expired}', f'{remote_folder}/{_dump_name(0)}'])

  cleanup_old_backups(server=True)

  assert deleted == [expired]


def test_cleanup_keeps_files_it_cannot_date(monkeypatch):
  deleted = _collect_deletes(
    monkeypatch,
    ['/backup/prod/postgres-backup/backup-manuale.dump', '/backup/prod/postgres-backup/note.txt'],
  )

  cleanup_old_backups()

  assert deleted == []


def _use_fallback_folder(monkeypatch, tmp_path, create=False):
  fallback = tmp_path / 'fallback'
  if create:
    fallback.mkdir()
  monkeypatch.setattr(backup_module, 'BACKUP_FALLBACK_FOLDER', str(fallback))
  return fallback


def _collect_telegram(monkeypatch):
  messages = []
  monkeypatch.setattr(backup_module, 'send_telegram_message', messages.append)
  return messages


def _collect_uploads(monkeypatch):
  uploaded = []
  monkeypatch.setattr(backup_module, 'upload_file', lambda content, filename, *args: uploaded.append(filename))
  return uploaded


def _run_threads_inline(monkeypatch):
  """db_backup lavora in un thread daemon: qui lo si esegue in linea.

  Senza questo non ci sarebbe modo di attendere la fine del backup, e un
  eventuale errore nel thread sparirebbe senza far fallire il test.
  """

  class InlineThread:
    def __init__(self, target=None, daemon=None):
      self._target = target

    def start(self):
      self._target()

  monkeypatch.setattr(backup_module.threading, 'Thread', InlineThread)


def _no_space_error(*args, **kwargs):
  raise subprocess.CalledProcessError(
    11, 'rsync', stderr='rsync: write failed on "/backup/prod/postgres-backup": No space left on device (28)'
  )


def _prepare_backup(monkeypatch, tmp_path, dump_name):
  dump = tmp_path / dump_name
  dump.write_bytes(b'dump-di-prova')

  monkeypatch.setattr(backup_module, 'BACKUP_FOLDER', str(tmp_path / 'destinazione'))
  monkeypatch.setattr(backup_module, 'data_export', lambda db_url: str(dump))
  monkeypatch.setattr(backup_module, 'cleanup_old_backups', lambda *args, **kwargs: None)
  _run_threads_inline(monkeypatch)
  return dump


def test_disk_full_moves_the_dump_to_the_fallback_folder(monkeypatch, tmp_path):
  fallback = _use_fallback_folder(monkeypatch, tmp_path)
  messages = _collect_telegram(monkeypatch)
  dump = _prepare_backup(monkeypatch, tmp_path, _dump_name(0))
  monkeypatch.setattr(backup_module, 'upload_file', _no_space_error)
  monkeypatch.setattr(backup_module, 'delete_file', lambda *args, **kwargs: pytest.fail('il dump non va cancellato'))

  db_backup('postgresql://user:pwd@localhost/db', server=True)

  assert not dump.exists()
  assert [path.name for path in fallback.iterdir()] == [dump.name]

  assert len(messages) == 1
  assert 'spazio esaurito' in messages[0]
  assert 'No space left on device' in messages[0]
  assert str(fallback / dump.name) in messages[0]


def test_notification_arrives_even_when_the_fallback_fails(monkeypatch, tmp_path):
  """Il disco locale pieno e' l'unico caso in cui il dump si perde davvero.

  Anche allora il messaggio deve partire: e' l'unico modo per sapere che non
  esiste piu' nessuna copia.
  """
  occupato = tmp_path / 'occupato'
  occupato.write_text("non e' una cartella")
  monkeypatch.setattr(backup_module, 'BACKUP_FALLBACK_FOLDER', str(occupato / 'fallback'))

  messages = _collect_telegram(monkeypatch)
  dump = _prepare_backup(monkeypatch, tmp_path, _dump_name(0))
  monkeypatch.setattr(backup_module, 'upload_file', _no_space_error)

  db_backup('postgresql://user:pwd@localhost/db', server=True)

  assert dump.exists()
  assert len(messages) == 1
  assert 'Dump perso' in messages[0]


def test_dump_is_kept_on_any_upload_failure_not_only_disk_full(monkeypatch, tmp_path):
  fallback = _use_fallback_folder(monkeypatch, tmp_path)
  messages = _collect_telegram(monkeypatch)
  dump = _prepare_backup(monkeypatch, tmp_path, _dump_name(0))

  def ssh_down(*args, **kwargs):
    raise subprocess.CalledProcessError(255, 'ssh', stderr='ssh: connect to host backup port 22: Connection refused')

  monkeypatch.setattr(backup_module, 'upload_file', ssh_down)

  db_backup('postgresql://user:pwd@localhost/db', server=True)

  assert [path.name for path in fallback.iterdir()] == [dump.name]
  assert 'spazio esaurito' not in messages[0]
  assert 'Dump salvato in locale' in messages[0]


def test_failure_before_the_dump_only_notifies(monkeypatch, tmp_path):
  fallback = _use_fallback_folder(monkeypatch, tmp_path)
  messages = _collect_telegram(monkeypatch)
  _run_threads_inline(monkeypatch)
  monkeypatch.setattr(backup_module, 'BACKUP_FOLDER', '')

  db_backup('postgresql://user:pwd@localhost/db', server=True)

  assert not fallback.exists()
  assert len(messages) == 1
  assert 'BACKUP_FOLDER non configurata' in messages[0]


def test_flush_uploads_pending_dumps_from_the_oldest(monkeypatch, tmp_path):
  fallback = _use_fallback_folder(monkeypatch, tmp_path, create=True)
  messages = _collect_telegram(monkeypatch)
  uploaded = _collect_uploads(monkeypatch)

  older, newer = _dump_name(3), _dump_name(1)
  for name in (newer, older):
    (fallback / name).write_bytes(b'dump-di-prova')

  flush_fallback_backups(server=True)

  assert uploaded == [older, newer]
  assert list(fallback.iterdir()) == []
  assert 'Dump di Fallback Ricaricati (2)' in messages[0]


def test_flush_keeps_the_dump_when_the_destination_is_still_full(monkeypatch, tmp_path):
  fallback = _use_fallback_folder(monkeypatch, tmp_path, create=True)
  messages = _collect_telegram(monkeypatch)
  monkeypatch.setattr(backup_module, 'upload_file', _no_space_error)

  for days_ago in (3, 1):
    (fallback / _dump_name(days_ago)).write_bytes(b'dump-di-prova')

  flush_fallback_backups(server=True)

  assert len(list(fallback.iterdir())) == 2
  assert len(messages) == 1
  assert 'Recupero Dump di Fallback Fallito' in messages[0]


def test_flush_ignores_files_that_are_not_dumps(monkeypatch, tmp_path):
  fallback = _use_fallback_folder(monkeypatch, tmp_path, create=True)
  messages = _collect_telegram(monkeypatch)
  uploaded = _collect_uploads(monkeypatch)

  (fallback / 'note.txt').write_text('appunti')
  (fallback / 'backup-manuale.dump').write_bytes(b'dump-di-prova')

  flush_fallback_backups()

  assert uploaded == []
  assert messages == []
  assert len(list(fallback.iterdir())) == 2


def test_flush_does_nothing_without_a_fallback_folder(monkeypatch, tmp_path):
  _use_fallback_folder(monkeypatch, tmp_path)
  messages = _collect_telegram(monkeypatch)
  uploaded = _collect_uploads(monkeypatch)

  flush_fallback_backups(server=True)

  assert uploaded == []
  assert messages == []


def test_successful_backup_recovers_the_pending_dumps(monkeypatch, tmp_path):
  fallback = _use_fallback_folder(monkeypatch, tmp_path, create=True)
  messages = _collect_telegram(monkeypatch)
  uploaded = _collect_uploads(monkeypatch)

  pending = _dump_name(2)
  (fallback / pending).write_bytes(b'dump-di-prova')

  dump = _prepare_backup(monkeypatch, tmp_path, _dump_name(0))
  deleted = []
  monkeypatch.setattr(backup_module, 'delete_file', lambda filename, *args, **kwargs: deleted.append(filename))

  db_backup('postgresql://user:pwd@localhost/db', server=True)

  assert uploaded == [dump.name, pending]
  assert deleted == [str(dump)]
  assert list(fallback.iterdir()) == []
  assert 'Dump di Fallback Ricaricati (1)' in messages[0]


def test_cleanup_passes_folder_and_server_to_delete_file(monkeypatch):
  captured = []
  monkeypatch.setattr(backup_module, 'get_all_filenames', lambda *args, **kwargs: [f'/srv/dumps/{_dump_name(90)}'])
  monkeypatch.setattr(backup_module, 'delete_file', lambda *args, **kwargs: captured.append(args))

  cleanup_old_backups(server=True)

  filename, folder, server, subfolder, ignore_dev = captured[0]
  assert filename.endswith('.dump')
  assert folder == backup_module.BACKUP_FOLDER
  assert server is True
  assert subfolder == '/srv/dumps'
  assert ignore_dev is True
