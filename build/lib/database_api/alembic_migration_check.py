import os
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, Table, Column, String, MetaData, inspect, text


def alembic_migration_check(engine: Engine, Session):
  migration_files = get_migration_files()
  if len(migration_files) > 0:
    if not exists_alembic_table(engine):
      command.upgrade(Config('alembic.ini'), 'head')

    if get_last_version(migration_files) != get_current_alembic_version(Session):
      raise Exception('Alembic is not updated')


def exists_alembic_table(engine: Engine) -> bool:
  with engine.connect() as connection:
    return inspect(connection).has_table('alembic_version', schema='public')


def get_current_alembic_version(Session) -> str:
  with Session() as session:
    return session.execute(text('SELECT version_num FROM alembic_version')).scalar()


def get_migration_files():
  folder = os.path.join('src', 'database', 'alembic', 'versions')
  return [f for f in os.listdir(folder) if f.endswith('.py')]


def get_last_version(migrations) -> str:
  folder = os.path.join('src', 'database', 'alembic', 'versions')
  revisions = []
  down_revisions = []
  for migration in migrations:
    with open(os.path.join(folder, migration), 'r') as f:
      content = f.read()
    namespace = {}
    exec(content, namespace)
    if 'revision' in namespace and 'down_revision' in namespace:
      revisions.append(namespace['revision'])
      down_revisions.append(namespace['down_revision'])
  last_migrations = [rev for rev in revisions if rev not in down_revisions]
  if len(last_migrations) != 1:
    raise Exception(f'Not found last migration on path {folder}')
  return last_migrations[0]


def force_last_version(engine: Engine, last_version: str):
  metadata = MetaData()
  alembic_version = Table(
    'alembic_version', metadata, Column('version_num', String(32), primary_key=True, nullable=False)
  )
  metadata.create_all(engine)
  with engine.connect() as connection:
    connection.execute(alembic_version.insert().values(version_num=last_version))
