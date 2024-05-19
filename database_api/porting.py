import os
import zipfile
from datetime import datetime
from sqlalchemy import Engine, inspect
from psycopg2.extensions import cursor as PgCursor


def data_export_(engine: Engine):
  for table in get_tables(engine):
    export_data_to_dump(engine, table, f'{table}.csv')
  zip_filename = f'{datetime.now().strftime("%y%m%d%H%M%S")}.zip'
  with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
    for table in get_tables(engine):
      csv_filename = f'{table}.csv'
      export_data_to_dump(engine, table, csv_filename)
      zipf.write(csv_filename)
      os.remove(csv_filename)
  return zip_filename


def data_import_(engine: Engine, zip_filename: str):
  with zipfile.ZipFile(zip_filename, 'r') as zipf:
    zipf.extractall()
    for file_name in zipf.namelist():
      if file_name.endswith('.csv'):
        table_name = os.path.splitext(file_name)[0]
        import_data_from_dump(engine, table_name, file_name)
        os.remove(file_name)


def export_data_to_dump(engine: Engine, table_name: str, dump_file: str):
  conn = engine.raw_connection()
  cursor = conn.cursor()
  with open(dump_file, 'w') as f:
    cursor.copy_expert(f'COPY "{table_name}" TO STDOUT WITH CSV HEADER', f)
  cursor.close()
  conn.close()


def import_data_from_dump(engine: Engine, table_name: str, dump_file: str):
  conn = engine.raw_connection()
  try:
    cursor = conn.cursor()
    cursor.execute(f'TRUNCATE TABLE "{table_name}"')
    with open(dump_file, 'r') as f:
      next(f)
      cursor.copy_from(f, table_name, sep=',')
    conn.commit()
    update_sequence(cursor, table_name)
  finally:
    cursor.close()
    conn.close()


def get_tables(engine: Engine) -> list[str]:
  return inspect(engine).get_table_names()


def update_sequence(cursor: PgCursor, table_name: str):
  cursor.execute(f"""
    SELECT kcu.column_name
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name
    WHERE tc.table_name = '{table_name}' AND tc.constraint_type = 'PRIMARY KEY';
  """)
  primary_key_column = cursor.fetchone()
  
  if primary_key_column:
    sequence_name = f"{table_name}_{primary_key_column[0]}_seq"
    cursor.execute(f"""
      SELECT 1
      FROM information_schema.sequences
      WHERE sequence_name = '{sequence_name}';
    """)
    if cursor.fetchone():
      cursor.execute(f"""
        SELECT setval('{sequence_name}', (SELECT COALESCE(MAX("{primary_key_column[0]}"), 1) FROM "{table_name}"));
      """)
      cursor.connection.commit()
