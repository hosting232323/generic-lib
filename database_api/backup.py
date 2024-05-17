from sqlalchemy import Engine


def export_data_to_dump(engine: Engine, table_name, dump_file):
  conn = engine.raw_connection()
  cursor = conn.cursor()
  cursor.copy_expert(f"COPY {table_name} TO STDOUT WITH CSV HEADER", open(dump_file, 'w'))
  cursor.close()
  conn.close()


def import_data_from_dump(engine: Engine, table_name, dump_file):
  conn = engine.raw_connection()
  cursor = conn.cursor()
  with open(dump_file, 'r') as f:
    next(f)
    cursor.copy_from(f, table_name, sep=',')
  conn.commit()
  cursor.close()
  conn.close()
