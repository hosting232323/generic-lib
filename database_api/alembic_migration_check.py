import os
import re
from sqlalchemy import Engine, Table, Column, String


def check_and_apply_migrations(engine: Engine):
  last_version = get_last_version()
  if last_version:
    if not engine.dialect.has_table(engine, 'alembic_version', schema='public'):
      force_last_version(engine, last_version)


def get_last_version():
  last_migration = None
  folder = os.path.join('src', 'database', 'alembic', 'versions')
  migrations = [f for f in os.listdir(folder) if f.endswith('.py')]
  for migration in migrations:
    with open(os.path.join(folder, migration), 'r') as f:
      content = f.read()
    match = re.compile(r'revision:\s*[\'](.+)[\']').match(content)
    if match:
      version = match.group(1)
      if last_migration is None or version > last_migration:
        last_migration = version
  return last_migration


def force_last_version(engine: Engine, last_version: str):
  alembic_version = Table(
    'alembic_version',
    Column('version_num', String(32), primary_key=True)
  )
  alembic_version.create(engine)
  with engine.connect() as conn:
    conn.execute(alembic_version.insert(), [{'version_num': last_version}])