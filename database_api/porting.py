import os
import csv
import json
import shutil
import zipfile
from datetime import datetime
from collections import deque
from sqlalchemy import Engine, inspect, text
from psycopg2.extensions import cursor as PgCursor


# Gestire la raw connection con un decorator

def data_export_(engine: Engine):
  json_backup_dir = 'json_backup'
  zip_filename = f'{datetime.now().strftime("%y%m%d%H%M%S")}.zip'
  with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
    for table in get_tables(engine):
      if table != 'alembic_version':
        csv_filename = f'{table}.csv'
        export_data_to_dump(engine, table, csv_filename)
        zipf.write(csv_filename)
        os.remove(csv_filename)
        if os.path.exists(json_backup_dir):
          for root, dirs, files in os.walk(json_backup_dir):
            for file in files:
              file_path = os.path.join(root, file)
              arcname = os.path.relpath(file_path, json_backup_dir)
              zipf.write(file_path, arcname=os.path.join(json_backup_dir, arcname))
          shutil.rmtree(json_backup_dir)
  return zip_filename


def data_import_(engine: Engine, zip_filename: str):
  with zipfile.ZipFile(zip_filename, 'r') as zipf:
    zipf.extractall()
    table_files = {os.path.splitext(file_name)[0]: file_name for file_name in zipf.namelist() if file_name.endswith('.csv')}
    ordered_tables = get_ordered_tables_by_dependency(engine, table_files.keys())
    for table_name in ordered_tables:
      truncate_table(engine, table_name)
    for table_name in list(reversed(ordered_tables)):
      import_data_from_dump(engine, table_name, table_files[table_name])
      os.remove(table_files[table_name])
    if os.path.exists('json_backup'):
      import_json_data(engine, 'json_backup')


def export_data_to_dump(engine: Engine, table_name: str, dump_file: str):
  conn = engine.raw_connection()
  cursor = conn.cursor()
  cursor.execute(f"""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = '{table_name}';
  """)
  columns = cursor.fetchall()
  column_names = [col[0] for col in columns]
  with open(dump_file, 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f, delimiter='\t')
    writer.writerow(column_names)
    cursor.execute(f'SELECT {", ".join(column_names)} FROM "{table_name}";')
    for row in cursor.fetchall():
      row_data = list(row)
      for idx, col in enumerate(columns):
        if col[1] in ['json', 'jsonb']:
          row_data[idx] = '{}'
      writer.writerow(row_data)
  json_columns = [col[0] for col in columns if col[1] in ['json', 'jsonb']]
  if json_columns:
    json_backup_dir = os.path.join('json_backup', table_name)
    os.makedirs(json_backup_dir, exist_ok=True)
    json_columns_str = ', '.join(f'"{col}"' for col in json_columns)
    cursor.execute(f'SELECT id, {json_columns_str} FROM "{table_name}";')
    for row in cursor.fetchall():
      row_id = row[0]
      row = row[1:]
      for idx, json_col in enumerate(json_columns):
        json_data = row[idx]
        if json_data:
          json_file_path = os.path.join(json_backup_dir, f'{json_col} {row_id}.json')
          with open(json_file_path, 'w', encoding='utf-8') as json_file:
            json.dump(json_data, json_file, ensure_ascii=False, indent=2)
  cursor.close()
  conn.close()


def truncate_table(engine: Engine, table_name: str):
  conn = engine.raw_connection()
  cursor = conn.cursor()
  cursor.execute(f'DELETE FROM "{table_name}"')
  cursor.close()
  conn.commit()
  conn.close()


def import_data_from_dump(engine: Engine, table_name: str, dump_file: str):
  conn = engine.raw_connection()
  try:
    cursor = conn.cursor()
    with open(dump_file, 'r', encoding='utf-8') as f:
      reader = csv.reader(f, delimiter='\t')
      columns_str = ','.join(next(reader))
      cursor.copy_expert(f'''
        COPY "{table_name}" ({columns_str}) FROM STDIN WITH (FORMAT CSV, DELIMITER \'\t\')
      ''', f)
    conn.commit()
    update_sequence(cursor, table_name)
  finally:
    cursor.close()
    conn.close()


def import_json_data(engine: Engine, extract_to: str):
  conn = engine.connect()
  for root, dirs, files in os.walk(extract_to):
    for dir in dirs:
      table_path = os.path.join(root, dir)
      for json_file in os.listdir(table_path):
        if json_file.endswith('.json'):
          json_col, row_id = json_file.replace('.json', '').split(' ')
          with open(os.path.join(table_path, json_file), 'r', encoding='utf-8') as f:
            json_data = json.load(f)
          conn.execute(text(f'''
            UPDATE "{dir}"
            SET "{json_col}" = :json_data
            WHERE id = :row_id
          '''), {
            'json_data': json.dumps(json_data),
            'row_id': row_id
          })
          conn.commit()
  conn.close()
  shutil.rmtree(extract_to)


def get_tables(engine: Engine) -> list[str]:
  return inspect(engine).get_table_names()


def get_ordered_tables_by_dependency(engine: Engine, table_names: list[str]):
  inspector = inspect(engine)
  dependencies = {}
  for table_name in table_names:
    foreign_keys = inspector.get_foreign_keys(table_name)
    dependencies[table_name] = []
    for fk in foreign_keys:
      dependencies[table_name].append(fk['referred_table'])
  return topological_sort(dependencies)


def topological_sort(dependencies: dict[str, list[str]]):
  in_degree = {table: 0 for table in dependencies}
  for table in dependencies:
    for dep in dependencies[table]:
      in_degree[dep] += 1
  queue = deque([table for table in in_degree if in_degree[table] == 0])
  sorted_list = []
  while queue:
    table = queue.popleft()
    sorted_list.append(table)
    for dep in dependencies[table]:
      in_degree[dep] -= 1
      if in_degree[dep] == 0:
        queue.append(dep)
  if len(sorted_list) == len(dependencies):
    return sorted_list
  else:
    raise Exception("A cycle was detected in the dependency graph")


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
