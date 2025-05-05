import sys
import enum
import traceback
from contextlib import contextmanager
from datetime import datetime, date, time
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import create_engine, Column, Integer, DateTime, func

from .backup import schedule_backup
from .porting import data_export_, data_import_
from .alembic_migration_check import alembic_migration_check


engine = None
Base = declarative_base()


def set_database(url: str, sub_folder: str|None = None):
  global engine
  engine = create_engine(url, pool_pre_ping=True)

  alembic_migration_check(engine, Session)
  if sub_folder:
    schedule_backup(engine, sub_folder)

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
        if isinstance(getattr(self, attribute), enum.Enum):
          dict_obj[attribute] = getattr(self, attribute).value
        elif type(getattr(self, attribute)) is datetime:
          dict_obj[attribute] = getattr(self, attribute).strftime('%d/%m/%Y %H:%M')
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


class BaseEnum(enum.Enum):

  @classmethod
  def get_enum_option(cls, value):
    return next((p for p in cls if p.value == value), None)


def data_export():
  data_export_(set_database(sys.argv[1]))


def data_import():
  data_import_(set_database(sys.argv[1]), sys.argv[2])
