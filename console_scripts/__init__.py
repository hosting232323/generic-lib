import sys

from ..database_api import export
from .setup_project import setup_project_


def setup_project():
  generic_api_key = sys.argv[1]
  setup_project_(generic_api_key)


def db_export():
  export()
