import os
import configparser
from git import Repo
from sqlalchemy import Engine

from .porting import data_export_


def push_backup_to_git(engine: Engine):
  zip_file = os.path.join('.', data_export_(engine))
  repo = Repo('.')
  repo.index.add(zip_file)
  repo.index.commit(f'Adding backup ({zip_file.split(".")[0]})')
  origin = repo.remote(name='origin')
  origin.push()
