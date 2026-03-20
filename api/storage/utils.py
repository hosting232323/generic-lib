import os
from sqlalchemy import text
from database_api import set_database


def get_db_files(db_url, query):
  with set_database(db_url).connect() as conn:
    result = conn.execute(text(query))
    return {os.path.basename(row[0]).strip() for row in result if row[0]}
