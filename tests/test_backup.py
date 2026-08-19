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

## Fallback

Quando l'upload verso la destinazione finale non riesce (tipicamente l'hdd
esterno pieno) il dump appena prodotto e' l'unica copia esistente. Non va
cancellato: si mette da parte e la notifica Telegram parte comunque, dicendo
dove e' rimasto.

Con `server` il posto giusto e' la macchina di backup, in BACKUP_FALLBACK_FOLDER:
il disco che si e' riempito e' l'hdd esterno, non quello di sistema, e il dump
resta comunque sulla macchina dove lo si va a cercare per un restore. La
macchina che ospita il servizio non c'entra mai: e' quella che regge Postgres e
tutto il resto, e non e' un posto dove parcheggiare dump. Se la macchina di
backup non risponde il ripiego non avviene: il dump resta dov'e' nato e la
notifica lo dice, cosi' chi legge sa che deve intervenire.

Da li' il dump non si muove piu': quando l'hdd torna ad avere spazio sono i
backup nuovi a riprendere la strada giusta, i vecchi restano nel fallback. Sono
gia' al sicuro sulla stessa macchina, e riportarli in destinazione a posteriori
vorrebbe dire trasferimenti e notifiche per un file che nessuno cerca li'.

Quella cartella e' condivisa da tutti i progetti della macchina, ma i dump si
chiamano solo `%y%m%d%H%M%S.dump`: senza una sottocartella per progetto non ci
sarebbe modo di sapere da quale database viene il dump che si sta per
ripristinare.

## Soglia sul disco locale

Il dump nasce comunque qui e qui resta finche' non e' stato trasferito, e qui
finisce anche il ripiego quando la macchina di backup e' irraggiungibile:
riempire questo filesystem farebbe cadere la macchina, non solo il backup. Sopra
BACKUP_DISK_THRESHOLD il dump quindi non parte proprio.
"""

import os
import pytest
import subprocess
from pathlib import Path
from collections import namedtuple
from datetime import datetime, timedelta

from api.settings import BACKUP_DAYS, PROJECT_NAME
from database_api import backup as backup_module
from database_api.backup import cleanup_old_backups, db_backup, parse_backup_date


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
  """Riproduce il layout di produzione: la cartella del progetto dentro la root."""
  fallback = tmp_path / PROJECT_NAME
  if create:
    fallback.mkdir()
  monkeypatch.setattr(backup_module, 'BACKUP_FALLBACK_ROOT', str(tmp_path))
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


_DiskUsage = namedtuple('_DiskUsage', 'total used free')


def _fake_disk_usage(monkeypatch, used_percent: float):
  """Il controllo sulla soglia non deve dipendere dal disco di chi lancia i test."""
  total = 100 * 1024**3
  used = int(total * used_percent / 100)
  monkeypatch.setattr(backup_module.shutil, 'disk_usage', lambda path: _DiskUsage(total, used, total - used))


def _ssh_down(*args, **kwargs):
  raise subprocess.CalledProcessError(255, 'ssh', stderr='ssh: connect to host backup port 22: Connection refused')


def _prepare_backup(monkeypatch, tmp_path, dump_name):
  dump = tmp_path / dump_name
  dump.write_bytes(b'dump-di-prova')

  monkeypatch.setattr(backup_module, 'BACKUP_FOLDER', str(tmp_path / 'destinazione'))
  monkeypatch.setattr(backup_module, 'data_export', lambda db_url: str(dump))
  monkeypatch.setattr(backup_module, 'cleanup_old_backups', lambda *args, **kwargs: None)
  _fake_disk_usage(monkeypatch, 10)
  _run_threads_inline(monkeypatch)
  return dump


def _use_backup_server(monkeypatch, tmp_path, destination_error=None):
  """Mette in piedi la macchina di backup: destinazione e cartella di ripiego.

  Sono due cartelle di tmp_path perche' i test non hanno un host remoto, ma
  restano due posti distinti raggiungibili solo attraverso upload_file: nessun
  test puo' quindi cavarsela leggendo il dump dal disco locale, che e'
  esattamente cio' che il codice non deve piu' fare.

  La cartella di ripiego locale resta impostata a parte, sotto tmp_path/locale:
  in produzione ha lo stesso path su entrambe le macchine, qui va distinta per
  poter dire su quale delle due e' finito il dump.

  Va chiamata dopo _prepare_backup, di cui sovrascrive la destinazione.
  """
  destination = tmp_path / 'macchina-di-backup' / 'hdd-esterno' / 'postgres-backup'
  fallback = tmp_path / 'macchina-di-backup' / 'opt' / PROJECT_NAME

  monkeypatch.setattr(backup_module, 'BACKUP_FOLDER', str(destination.parent))
  monkeypatch.setattr(backup_module, 'BACKUP_FALLBACK_ROOT', str(fallback.parent))
  monkeypatch.setattr(backup_module, 'BACKUP_FALLBACK_FOLDER', str(tmp_path / 'locale' / PROJECT_NAME))

  def upload_file(content, filename, folder, server=None, subfolder=None, ignore_dev=None):
    target = Path(folder) / subfolder / filename
    if destination_error and target.parent == destination:
      destination_error()

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content.read())
    return str(target)

  monkeypatch.setattr(backup_module, 'upload_file', upload_file)

  return destination, fallback


def test_disk_full_keeps_the_dump_on_the_backup_server(monkeypatch, tmp_path):
  """Il caso per cui il fallback esiste: l'hdd esterno pieno.

  A riempirsi e' il disco della destinazione, non quello di sistema della
  macchina di backup: il dump resta li' accanto, e la macchina che ospita il
  servizio non deve vederselo arrivare addosso.
  """
  messages = _collect_telegram(monkeypatch)
  dump = _prepare_backup(monkeypatch, tmp_path, _dump_name(0))
  destination, fallback = _use_backup_server(monkeypatch, tmp_path, destination_error=_no_space_error)
  local_fallback = Path(backup_module.BACKUP_FALLBACK_FOLDER)
  monkeypatch.setattr(backup_module, 'delete_file', lambda *args, **kwargs: pytest.fail('il dump non va cancellato'))

  db_backup('postgresql://user:pwd@localhost/db', server=True)

  assert not dump.exists()
  assert [path.name for path in fallback.iterdir()] == [dump.name]
  assert not destination.exists()
  assert not local_fallback.exists()

  assert len(messages) == 1
  assert 'spazio esaurito' in messages[0]
  assert 'No space left on device' in messages[0]
  assert 'macchina di backup' in messages[0]
  assert str(fallback / dump.name) in messages[0]


def test_without_the_backup_server_the_dump_is_not_parked_on_the_service_machine(monkeypatch, tmp_path):
  """Senza ssh non c'e' ripiego: il dump non si scarica sul disco dei servizi.

  Quel disco regge Postgres e tutto il resto, non e' un deposito di dump. Il
  file resta dov'e' nato e la notifica dice qual e' il problema e dove trovarlo:
  da li' in poi e' una cosa da guardare a mano.
  """
  fallback = _use_fallback_folder(monkeypatch, tmp_path)
  messages = _collect_telegram(monkeypatch)
  dump = _prepare_backup(monkeypatch, tmp_path, _dump_name(0))
  monkeypatch.setattr(backup_module, 'upload_file', _ssh_down)

  db_backup('postgresql://user:pwd@localhost/db', server=True)

  assert dump.exists()
  assert not fallback.exists()
  assert len(messages) == 1
  assert 'Dump non messo al sicuro' in messages[0]
  assert 'Connection refused' in messages[0]
  assert str(dump) in messages[0]


def test_notification_arrives_even_when_the_fallback_folder_is_unusable(monkeypatch, tmp_path):
  """Senza `server` il ripiego e' l'unico posto disponibile: se manca, si avvisa."""
  occupato = tmp_path / 'occupato'
  occupato.write_text("non e' una cartella")
  monkeypatch.setattr(backup_module, 'BACKUP_FALLBACK_FOLDER', str(occupato / 'fallback'))

  messages = _collect_telegram(monkeypatch)
  dump = _prepare_backup(monkeypatch, tmp_path, _dump_name(0))
  monkeypatch.setattr(backup_module, 'upload_file', _no_space_error)

  db_backup('postgresql://user:pwd@localhost/db')

  assert dump.exists()
  assert len(messages) == 1
  assert 'Dump non messo al sicuro' in messages[0]


def test_dump_is_kept_on_any_upload_failure_not_only_disk_full(monkeypatch, tmp_path):
  messages = _collect_telegram(monkeypatch)
  dump = _prepare_backup(monkeypatch, tmp_path, _dump_name(0))

  def permission_denied():
    raise subprocess.CalledProcessError(23, 'rsync', stderr='rsync: mkstemp failed: Permission denied (13)')

  _, fallback = _use_backup_server(monkeypatch, tmp_path, destination_error=permission_denied)

  db_backup('postgresql://user:pwd@localhost/db', server=True)

  assert [path.name for path in fallback.iterdir()] == [dump.name]
  assert 'spazio esaurito' not in messages[0]
  assert 'Dump tenuto sulla macchina di backup' in messages[0]


def test_in_local_mode_the_dump_stays_on_the_machine(monkeypatch, tmp_path):
  """Senza `server` non c'e' nessun'altra macchina: il ripiego e' quello di casa."""
  fallback = _use_fallback_folder(monkeypatch, tmp_path)
  messages = _collect_telegram(monkeypatch)
  dump = _prepare_backup(monkeypatch, tmp_path, _dump_name(0))
  monkeypatch.setattr(backup_module, 'upload_file', _no_space_error)

  db_backup('postgresql://user:pwd@localhost/db')

  assert [path.name for path in fallback.iterdir()] == [dump.name]
  assert 'Dump tenuto nella cartella di ripiego' in messages[0]


def test_failure_before_the_dump_only_notifies(monkeypatch, tmp_path):
  fallback = _use_fallback_folder(monkeypatch, tmp_path)
  messages = _collect_telegram(monkeypatch)
  _run_threads_inline(monkeypatch)
  monkeypatch.setattr(backup_module, 'BACKUP_FOLDER', '')

  db_backup('postgresql://user:pwd@localhost/db', server=True)

  assert not fallback.exists()
  assert len(messages) == 1
  assert 'BACKUP_FOLDER non configurata' in messages[0]


def test_when_the_space_comes_back_only_the_new_dumps_take_the_right_road(monkeypatch, tmp_path):
  """L'hdd torna disponibile: il backup nuovo va in destinazione, il resto no.

  I dump gia' messi da parte restano nel fallback e nessuno li tocca: stanno
  sulla stessa macchina, sono raggiungibili per un restore, e riportarli in
  destinazione non aggiungerebbe niente se non trasferimenti e notifiche.
  """
  messages = _collect_telegram(monkeypatch)
  dump = _prepare_backup(monkeypatch, tmp_path, _dump_name(0))
  destination, fallback = _use_backup_server(monkeypatch, tmp_path)

  parcheggiato = _dump_name(2)
  fallback.mkdir(parents=True)
  (fallback / parcheggiato).write_bytes(b'dump-di-prova')

  deleted = []
  monkeypatch.setattr(backup_module, 'delete_file', lambda filename, *args, **kwargs: deleted.append(filename))

  db_backup('postgresql://user:pwd@localhost/db', server=True)

  assert [path.name for path in destination.iterdir()] == [dump.name]
  assert [path.name for path in fallback.iterdir()] == [parcheggiato]
  assert deleted == [str(dump)]
  assert messages == []


def test_backup_does_not_start_when_the_local_disk_is_over_the_threshold(monkeypatch, tmp_path):
  _use_fallback_folder(monkeypatch, tmp_path)
  messages = _collect_telegram(monkeypatch)
  uploaded = _collect_uploads(monkeypatch)
  _prepare_backup(monkeypatch, tmp_path, _dump_name(0))
  monkeypatch.setattr(backup_module, 'BACKUP_DISK_THRESHOLD', 90)
  monkeypatch.setattr(
    backup_module, 'data_export', lambda db_url: pytest.fail('il dump non va prodotto con il disco quasi pieno')
  )
  _fake_disk_usage(monkeypatch, 95)

  db_backup('postgresql://user:pwd@localhost/db', server=True)

  assert uploaded == []
  assert len(messages) == 1
  assert 'Bloccato' in messages[0]
  assert '95.0%' in messages[0]
  assert 'soglia 90%' in messages[0]
  assert '5.0 GB liberi' in messages[0]


def test_backup_runs_when_the_local_disk_is_under_the_threshold(monkeypatch, tmp_path):
  _use_fallback_folder(monkeypatch, tmp_path)
  messages = _collect_telegram(monkeypatch)
  uploaded = _collect_uploads(monkeypatch)
  dump = _prepare_backup(monkeypatch, tmp_path, _dump_name(0))
  monkeypatch.setattr(backup_module, 'delete_file', lambda *args, **kwargs: None)
  monkeypatch.setattr(backup_module, 'BACKUP_DISK_THRESHOLD', 90)
  _fake_disk_usage(monkeypatch, 89.9)

  db_backup('postgresql://user:pwd@localhost/db', server=True)

  assert uploaded == [dump.name]
  assert messages == []


def test_the_threshold_blocks_the_backup_as_soon_as_it_is_reached(monkeypatch, tmp_path):
  _use_fallback_folder(monkeypatch, tmp_path)
  messages = _collect_telegram(monkeypatch)
  _prepare_backup(monkeypatch, tmp_path, _dump_name(0))
  monkeypatch.setattr(backup_module, 'BACKUP_DISK_THRESHOLD', 90)
  _fake_disk_usage(monkeypatch, 90)

  db_backup('postgresql://user:pwd@localhost/db', server=True)

  assert 'Bloccato' in messages[0]


def test_a_blocked_backup_leaves_the_dumps_already_kept_aside(monkeypatch, tmp_path):
  """Il blocco riguarda il dump nuovo, non quelli gia' messi da parte."""
  fallback = _use_fallback_folder(monkeypatch, tmp_path, create=True)
  messages = _collect_telegram(monkeypatch)
  uploaded = _collect_uploads(monkeypatch)
  _prepare_backup(monkeypatch, tmp_path, _dump_name(0))
  monkeypatch.setattr(backup_module, 'BACKUP_DISK_THRESHOLD', 90)
  _fake_disk_usage(monkeypatch, 97)

  parcheggiato = _dump_name(2)
  (fallback / parcheggiato).write_bytes(b'dump-di-prova')

  db_backup('postgresql://user:pwd@localhost/db', server=True)

  assert uploaded == []
  assert [path.name for path in fallback.iterdir()] == [parcheggiato]
  assert len(messages) == 1
  assert 'Bloccato' in messages[0]


def test_the_same_filesystem_is_checked_once(monkeypatch, tmp_path):
  """Cartella di lavoro e fallback stanno di norma sullo stesso disco."""
  fallback = _use_fallback_folder(monkeypatch, tmp_path, create=True)
  monkeypatch.chdir(tmp_path)

  assert backup_module.local_disk_paths() == [os.getcwd()]
  assert fallback.exists()


def test_a_fallback_folder_that_does_not_exist_yet_is_not_checked(monkeypatch, tmp_path):
  _use_fallback_folder(monkeypatch, tmp_path)
  monkeypatch.chdir(tmp_path)

  assert backup_module.local_disk_paths() == [os.getcwd()]


def test_the_fallback_folder_is_separated_per_project(monkeypatch, tmp_path):
  """La cartella e' condivisa da tutti i progetti della macchina, i dump no.

  I nomi contengono solo il timestamp: buttati tutti insieme, al momento del
  restore non ci sarebbe modo di sapere da quale database viene il dump che si
  sta per ripristinare.
  """
  assert backup_module.BACKUP_FALLBACK_FOLDER == os.path.join(backup_module.BACKUP_FALLBACK_ROOT, PROJECT_NAME)

  _collect_telegram(monkeypatch)
  dump = _prepare_backup(monkeypatch, tmp_path, _dump_name(0))
  _, fallback = _use_backup_server(monkeypatch, tmp_path, destination_error=_no_space_error)

  db_backup('postgresql://user:pwd@localhost/db', server=True)

  assert fallback.name == PROJECT_NAME
  assert [path.name for path in fallback.iterdir()] == [dump.name]


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
