import sys
import traceback
from sqlalchemy import create_engine
from contextlib import contextmanager
from sqlalchemy.orm import sessionmaker

from .backup import data_export_, data_import_
from .alembic_migration_check import alembic_migration_check


engine = None


def set_database(url):
  global engine
  engine = create_engine(url, pool_pre_ping=True)
  alembic_migration_check(engine, Session)
  return engine


@contextmanager
def Session():
  if engine is None:
    raise Exception('Database engine not initialized')
  session = sessionmaker(bind=engine)()
  try:
    yield session
  except Exception:
    traceback.print_exc()
    session.rollback()
  finally:
    session.close()


def data_export():
  data_export_(set_database(sys.argv[1]))


def data_import():
  data_import_(set_database(sys.argv[1]), sys.argv[2])
