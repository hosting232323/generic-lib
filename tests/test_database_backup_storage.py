import os

from database_api import backup


class ImmediateThread:
  def __init__(self, target, **kwargs):
    self.target = target

  def start(self):
    self.target()


def test_db_backup_retention_uses_configured_subfolder(tmp_path, monkeypatch):
  monkeypatch.chdir(tmp_path)
  (tmp_path / '260101000000.dump').write_bytes(b'dump')

  backup_root = str(tmp_path / 'backups')
  monkeypatch.setattr(backup, 'BACKUP_FOLDER', backup_root)
  monkeypatch.setattr(backup, 'BACKUP_DAYS', 1)
  monkeypatch.setattr(backup, 'data_export', lambda db_url: '260101000000.dump')
  monkeypatch.setattr(backup.threading, 'Thread', ImmediateThread)
  monkeypatch.setattr(backup, 'upload_file', lambda *args, **kwargs: None)
  monkeypatch.setattr(
    backup,
    'get_all_filenames',
    lambda *args, **kwargs: [
      os.path.join(backup_root, 'postgres-backup', '240101000000.dump'),
      os.path.join(backup_root, 'postgres-backup', '260101000000.dump'),
    ],
  )

  deleted = []
  monkeypatch.setattr(backup, 'delete_file', lambda *args, **kwargs: deleted.append((args, kwargs)))

  backup.db_backup('postgresql://database')

  assert deleted[0] == (('260101000000.dump', ''), {'ignore_dev': True})
  assert deleted[1] == (
    (
      '240101000000.dump',
      backup_root,
      None,
      os.path.join(backup_root, 'postgres-backup'),
      True,
    ),
    {},
  )
