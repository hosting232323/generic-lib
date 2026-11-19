"""Test della retention e del fallback locale dei dump del database.

## Retention

I dump stanno in un repository restic, cifrato con RESTIC_PASSWORD: la
retention e' `restic forget --keep-within BACKUP_DAYS`, che conta i giorni dallo
snapshot piu' recente. Qui si controlla solo che parta sul repository giusto;
i comandi restic sono coperti in test_db_dump_storage.py.

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

Quella cartella e' condivisa da tutti i progetti della macchina, ma ogni dump
nel repository si chiama sempre `database.dump`: senza una sottocartella per
progetto non ci sarebbe modo di sapere da quale database viene il dump che si
sta per ripristinare. Anche il ripiego e' un repository restic: il dump non e'
mai in chiaro sulla macchina di backup.

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

from api.settings import PROJECT_NAME
from database_api import backup as backup_module
from database_api.backup import cleanup_old_backups, db_backup, fetch_backup


def _dump_name(days_ago: float) -> str:
  return f'{(datetime.now() - timedelta(days=days_ago)).strftime("%y%m%d%H%M%S")}.dump'


def test_cleanup_runs_on_the_db_backup_repository(monkeypatch):
  captured = []
  monkeypatch.setattr(backup_module, 'BACKUP_FOLDER', '/srv/backup/italco')
  monkeypatch.setattr(backup_module, 'cleanup_db_dumps', lambda *args: captured.append(args))

  cleanup_old_backups(server=True)

  assert captured == [(os.path.join('/srv/backup/italco', 'db-backup'), True)]


def test_fetch_backup_reads_the_dump_from_the_repository(monkeypatch, tmp_path):
  captured = []
  monkeypatch.setattr(backup_module, 'BACKUP_FOLDER', '/srv/backup/italco')
  monkeypatch.setattr(backup_module, 'download_db_dump', lambda *args: captured.append(args) or args[2])

  output = str(tmp_path / 'restore.dump')
  assert fetch_backup(output, 'a1b2c3d4', server=True) == output
  assert captured == [(os.path.join('/srv/backup/italco', 'db-backup'), 'database.dump', output, 'a1b2c3d4', True)]


def test_fetch_backup_without_backup_folder_fails(monkeypatch, tmp_path):
  monkeypatch.setattr(backup_module, 'BACKUP_FOLDER', '')

  with pytest.raises(ValueError, match='BACKUP_FOLDER'):
    fetch_backup(str(tmp_path / 'restore.dump'))


def _use_fallback_folder(monkeypatch, tmp_path, create=False):
  """Riproduce il layout di produzione: la cartella del progetto dentro la root.

  Restituisce il repository restic di ripiego, dentro la cartella del progetto.
  """
  fallback = tmp_path / PROJECT_NAME
  if create:
    (fallback / 'db-backup').mkdir(parents=True)
  monkeypatch.setattr(backup_module, 'BACKUP_FALLBACK_ROOT', str(tmp_path))
  monkeypatch.setattr(backup_module, 'BACKUP_FALLBACK_FOLDER', str(fallback))
  return fallback / 'db-backup'


def _collect_telegram(monkeypatch):
  messages = []
  monkeypatch.setattr(backup_module, 'send_telegram_message', messages.append)
  return messages


def _collect_uploads(monkeypatch):
  uploaded = []
  monkeypatch.setattr(
    backup_module, 'upload_db_dump', lambda file_path, *args: uploaded.append(os.path.basename(file_path))
  )
  return uploaded


def _fake_restic_upload(destination_error=None, destination=None):
  """Un repository restic finto: il dump finisce in <repository>/<nome del dump>.

  Basta per dire in quale repository e' arrivato, che e' tutto cio' che
  interessa a db_backup; i comandi restic veri sono in test_db_dump_storage.py.
  """

  def upload_db_dump(file_path, repository, filename, server=None):
    target = Path(repository)
    if destination_error and target == destination:
      destination_error()

    target.mkdir(parents=True, exist_ok=True)
    (target / os.path.basename(file_path)).write_bytes(Path(file_path).read_bytes())
    return str(target)

  return upload_db_dump


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
    1, 'restic', stderr='Fatal: unable to save snapshot: write /backup/db-backup/data/3f: no space left on device'
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
  destination = tmp_path / 'macchina-di-backup' / 'hdd-esterno' / 'db-backup'
  fallback = tmp_path / 'macchina-di-backup' / 'opt' / PROJECT_NAME / 'db-backup'

  monkeypatch.setattr(backup_module, 'BACKUP_FOLDER', str(destination.parent))
  monkeypatch.setattr(backup_module, 'BACKUP_FALLBACK_ROOT', str(fallback.parent.parent))
  monkeypatch.setattr(backup_module, 'BACKUP_FALLBACK_FOLDER', str(tmp_path / 'locale' / PROJECT_NAME))
  monkeypatch.setattr(backup_module, 'upload_db_dump', _fake_restic_upload(destination_error, destination))

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
  assert 'no space left on device' in messages[0]
  assert 'macchina di backup' in messages[0]
  assert str(fallback) in messages[0]


def test_without_the_backup_server_the_dump_is_not_parked_on_the_service_machine(monkeypatch, tmp_path):
  """Senza ssh non c'e' ripiego: il dump non si scarica sul disco dei servizi.

  Quel disco regge Postgres e tutto il resto, non e' un deposito di dump. Il
  file resta dov'e' nato e la notifica dice qual e' il problema e dove trovarlo:
  da li' in poi e' una cosa da guardare a mano.
  """
  fallback = _use_fallback_folder(monkeypatch, tmp_path)
  messages = _collect_telegram(monkeypatch)
  dump = _prepare_backup(monkeypatch, tmp_path, _dump_name(0))
  monkeypatch.setattr(backup_module, 'upload_db_dump', _ssh_down)

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
  destination = Path(backup_module.BACKUP_FOLDER) / 'db-backup'
  monkeypatch.setattr(backup_module, 'upload_db_dump', _fake_restic_upload(_no_space_error, destination))

  db_backup('postgresql://user:pwd@localhost/db')

  assert dump.exists()
  assert len(messages) == 1
  assert 'Dump non messo al sicuro' in messages[0]


def test_dump_is_kept_on_any_upload_failure_not_only_disk_full(monkeypatch, tmp_path):
  messages = _collect_telegram(monkeypatch)
  dump = _prepare_backup(monkeypatch, tmp_path, _dump_name(0))

  def permission_denied():
    raise subprocess.CalledProcessError(1, 'restic', stderr='Fatal: create repository failed: permission denied')

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
  destination = Path(backup_module.BACKUP_FOLDER) / 'db-backup'
  monkeypatch.setattr(backup_module, 'upload_db_dump', _fake_restic_upload(_no_space_error, destination))

  db_backup('postgresql://user:pwd@localhost/db')

  assert not dump.exists()
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

  assert fallback.parent.name == PROJECT_NAME
  assert [path.name for path in fallback.iterdir()] == [dump.name]


def test_the_notification_does_not_carry_the_database_password(monkeypatch):
  """La notifica dice quale database non e' stato salvato, mai con quale password."""
  messages = _collect_telegram(monkeypatch)
  _run_threads_inline(monkeypatch)
  monkeypatch.setattr(backup_module, 'BACKUP_FOLDER', '')

  db_backup('postgresql://italco:S3gr3ta!@db.interno:5432/italco', server=True)

  assert len(messages) == 1
  assert 'S3gr3ta!' not in messages[0]
  assert 'postgresql://italco:***@db.interno:5432/italco' in messages[0]


def test_the_password_is_hidden_also_in_the_error_details(monkeypatch, tmp_path):
  """pg_dump puo' riportare la riga di comando, e con lei l'URL intero."""
  db_url = 'postgresql://italco:S3gr3ta!@db.interno/italco'
  messages = _collect_telegram(monkeypatch)
  _fake_disk_usage(monkeypatch, 10)
  _run_threads_inline(monkeypatch)
  monkeypatch.setattr(backup_module, 'BACKUP_FOLDER', str(tmp_path))

  def failing_export(url):
    raise subprocess.CalledProcessError(1, 'pg_dump', stderr=f'pg_dump --dbname={url}: connessione fallita (S3gr3ta!)')

  monkeypatch.setattr(backup_module, 'data_export', failing_export)

  db_backup(db_url, server=True)

  assert len(messages) == 1
  assert 'S3gr3ta!' not in messages[0]
  assert 'connessione fallita' in messages[0]


@pytest.mark.parametrize(
  'db_url, expected',
  [
    ('postgresql://user:pwd@localhost/db', 'postgresql://user:***@localhost/db'),
    ('postgres://user:p%40ss@host:5433/db?sslmode=require', 'postgres://user:***@host:5433/db?sslmode=require'),
    ('postgresql://user@localhost/db', 'postgresql://user@localhost/db'),
    ('postgresql://localhost/db', 'postgresql://localhost/db'),
    ('postgresql://user:pwd@[::1]:5432/db', 'postgresql://user:***@[::1]:5432/db'),
    ('postgresql://user:pwd@DB.Interno:5432/db', 'postgresql://user:***@DB.Interno:5432/db'),
  ],
)
def test_mask_db_url(db_url, expected):
  assert backup_module.mask_db_url(db_url) == expected


def test_hide_db_password_hides_also_the_decoded_form_of_an_encoded_password():
  """Nell'URL la password e' p%40ss, ma pg_dump puo' stamparla come p@ss."""
  db_url = 'postgresql://italco:p%40ss@db.interno/italco'

  text = backup_module.hide_db_password('pg_dump: password p@ss rifiutata, URL ' + db_url, db_url)

  assert 'p@ss' not in text
  assert 'p%40ss' not in text
  assert 'postgresql://italco:***@db.interno/italco' in text
