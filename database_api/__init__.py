import sys
import enum
import traceback
from datetime import datetime, date
from contextlib import contextmanager
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import create_engine, Column, Integer, DateTime, func

from .porting import data_export_, data_import_
from .alembic_migration_check import alembic_migration_check


engine = None
Base = declarative_base()


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


class BaseEntity(Base):
  __abstract__ = True

  id = Column(Integer, primary_key=True, autoincrement=True)
  created_at = Column(DateTime(timezone=True), default=func.now())
  updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

  def to_dict(self):
    dict_obj = {}
    for attribute in self.__dict__:
      if getattr(self, attribute) is not None and attribute != '_sa_instance_state':
        dict_obj[attribute] = getattr(self, attribute)
        if isinstance(dict_obj[attribute], enum.Enum):
          dict_obj[attribute] = dict_obj[attribute].value
        elif type(dict_obj[attribute]) is datetime:
          dict_obj[attribute] = dict_obj[attribute].strftime("%d/%m/%Y %H:%M")
        elif type(dict_obj[attribute]) is date:
          dict_obj[attribute] = dict_obj[attribute].strftime("%Y-%m-%d")
    return dict_obj

  def __repr__(self):
    attributes = [f'{attr}: {getattr(self, attr)}' for attr in self.to_dict()]
    return f'{self.__class__.__name__} {{{", ".join(attributes)}}}'


def data_export():
  data_export_(set_database(sys.argv[1]))


def data_import():
  data_import_(set_database(sys.argv[1]), sys.argv[2])
