from .mailer import spam_mail_main
from .mismatch_files import check_aws_mismatch_, get_user_input
from database_api import data_export, data_import
from .project_setup import main as setup_project_main


def check_aws_mismatch():
  db_url, query, bucket_name, folder_input = get_user_input()
  check_aws_mismatch_(db_url, query, bucket_name, folder_input)


def db_export():
  data_export()


def db_import():
  data_import()


def setup_project():
  setup_project_main()


def spam_mail():
  spam_mail_main()
