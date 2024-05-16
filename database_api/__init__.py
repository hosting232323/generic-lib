import traceback
from sqlalchemy import create_engine
from contextlib import contextmanager
from sqlalchemy.orm import sessionmaker

from .alembic_migration_check import alembic_migration_check

# Ignore error!
from src.database.schema import Base


engine = None


def set_database(url):
  global engine
  engine = create_engine(url, pool_pre_ping=True)
  alembic_migration_check(engine, Session)
  Base.metadata.create_all(engine)
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


def export():
  print('ciao')
