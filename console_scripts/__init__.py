import sys

from .mailer import spam_mail_main
from .mismatch_files import run_comparison
from .project_setup import main as setup_project_main
from database_api.porting import data_export, data_import


def check_aws_mismatch():
  run_comparison()


def db_export():
  data_export(sys.argv[1])


def db_import():
  data_import(sys.argv[1], sys.argv[2])


def setup_project():
  setup_project_main()


def spam_mail():
  spam_mail_main()
