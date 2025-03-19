from .mailer import spam_mail_
from .mismatch_files import run_comparison
from database_api import data_export, data_import
from .project_setup import main as setup_project_main


def check_aws_mismatch():
  run_comparison()


def db_export():
  data_export()


def db_import():
  data_import()


def setup_project():
  setup_project_main()


def spam_mail():
  spam_mail_()
