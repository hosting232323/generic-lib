"""Test della retention dei dump del database.

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
"""

from datetime import datetime, timedelta

from api.settings import BACKUP_DAYS
from database_api import backup as backup_module
from database_api.backup import cleanup_old_backups, parse_backup_date


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
