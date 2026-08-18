import enum
import traceback
from zoneinfo import ZoneInfo
from contextvars import ContextVar
from contextlib import contextmanager
from datetime import datetime, date, time
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import create_engine, Column, Integer, DateTime, func

from .alembic_migration_check import alembic_migration_check


engine = None
Base = declarative_base()
_scope: ContextVar[dict] = ContextVar('database_api_scope', default=None)


def set_database(url: str, pool_size: int = 5, max_overflow: int = 10):
  global engine
  engine = create_engine(url, pool_size=pool_size, max_overflow=max_overflow, pool_pre_ping=True)

  alembic_migration_check(engine, Session)

  return engine


def current_scope() -> dict:
  return _scope.get() or {}


@contextmanager
def scope(**values):
  # Valori ribaltati su session.info di ogni Session aperta nel contesto corrente.
  # Serve a passare dati trasversali (es. il tenant attivo) agli event listener
  # senza farli attraversare ogni firma di funzione.
  token = _scope.set({**current_scope(), **values})
  try:
    yield
  finally:
    _scope.reset(token)


@contextmanager
def Session():
  if engine is None:
    raise Exception('Database engine not initialized')
  session = sessionmaker(bind=engine, expire_on_commit=False)()
  session.info.update(current_scope())
  try:
    yield session
  except Exception as e:
    traceback.print_exc()
    session.rollback()
    raise e
  finally:
    session.close()


class BaseEntity(Base):
  __abstract__ = True

  id = Column(Integer, primary_key=True, autoincrement=True)
  created_at = Column(DateTime(timezone=True), default=func.now())
  updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

  def to_dict(self):
    dict_obj = {}
    for attribute in self.__dict__:
      if getattr(self, attribute) is not None and attribute != '_sa_instance_state':
        if isinstance(getattr(self, attribute), enum.Enum):
          dict_obj[attribute] = getattr(self, attribute).value
        elif type(getattr(self, attribute)) is datetime:
          dict_obj[attribute] = getattr(self, attribute).astimezone(ZoneInfo('Europe/Rome')).strftime('%d/%m/%Y %H:%M')
        elif type(getattr(self, attribute)) is date:
          dict_obj[attribute] = getattr(self, attribute).strftime('%Y-%m-%d')
        elif type(getattr(self, attribute)) is time:
          dict_obj[attribute] = getattr(self, attribute).strftime('%H:%M:%S')
        elif type(getattr(self, attribute)) is bytes:
          continue
        else:
          dict_obj[attribute] = getattr(self, attribute)
    return dict_obj

  def __repr__(self):
    attributes = [f'{attr}: {getattr(self, attr)}' for attr in self.to_dict()]
    return f'{self.__class__.__name__} {{{", ".join(attributes)}}}'
