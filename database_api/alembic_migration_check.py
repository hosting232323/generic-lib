import os
from sqlalchemy import Engine, Table, Column, String, MetaData, inspect, text


def alembic_migration_check(engine: Engine, Session):
  if not exists_alembic_table(engine):
    raise Exception('Alembic table not exists')

  if get_last_version() != get_current_alembic_version(Session):
    raise Exception('Alembic is not updated')


def exists_alembic_table(engine: Engine) -> bool:
  with engine.connect() as connection:
    return inspect(connection).has_table('alembic_version', schema='public')


def get_current_alembic_version(Session) -> str:
  with Session() as session:
    return session.execute(text(
      'SELECT version_num FROM alembic_version'
    )).scalar()


def get_last_version() -> str:
  folder = os.path.join('src', 'database', 'alembic', 'versions')
  migrations = [f for f in os.listdir(folder) if f.endswith('.py')]
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
  last_migrations = []
  for revision in revisions:
    if not revision in down_revisions:
      last_migrations.append(revision)
  if len(last_migrations) != 1:
    raise Exception(f'Not found last migration on path {folder}')
  return last_migrations[0]


def force_last_version(engine: Engine, last_version: str):
  metadata = MetaData()
  alembic_version = Table(
    'alembic_version', metadata,
    Column('version_num', String(32), primary_key=True, nullable=False)
  )
  metadata.create_all(engine)
  with engine.connect() as connection:
    connection.execute(alembic_version.insert().values(version_num=last_version))
