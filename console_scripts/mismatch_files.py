import os
from sqlalchemy import text
from database_api import set_database
from api.storage import list_files_in_s3

def get_user_input():
    db_url = input('Inserisci l\'URL del database: ')
    query = input('Inserisci la query per ottenere i file: ')
    bucket_name = input('Inserisci il nome del bucket S3: ')
    folder_input = input('Folder selezionato: (None, prod, test) (default: None): ') or 'None'
    return db_url, query, bucket_name, folder_input

def parse_is_dev(folder_input):
    """
    Converte l'input del folder selezionato in valori booleani o None:
    - 'None' -> None
    - 'test' -> True
    - 'prod' -> False
    """
    folder_input = folder_input.lower()
    if folder_input == "none":
        return None
    elif folder_input == "test":
        return True
    elif folder_input == "prod":
        return False
    else:
        raise ValueError("Input non valido. Scegli tra 'None', 'prod', o 'test'.")

def get_db_files(db_url, query):
    with set_database(db_url).connect() as conn:
        result = conn.execute(text(query))
        return {os.path.basename(url) for url in {row[0] for row in result}}

def get_s3_files(bucket_name, is_dev=None):
    """
    Cerca i file su S3 rispettando il prefisso selezionato:
    - None -> Nessuna sottocartella
    - True -> Sottocartella 'test/'
    - False -> Sottocartella 'prod/'
    """
    folder_prefix = ''
    if is_dev is not None:
        folder_prefix = 'test/' if is_dev else 'prod/'

    return {os.path.basename(url) for url in list_files_in_s3(bucket_name, folder=folder_prefix)}

def run_comparison():
    db_url, query, bucket_name, folder_input = get_user_input()
    is_dev = parse_is_dev(folder_input)

    db_files = get_db_files(db_url, query)
    s3_files = get_s3_files(bucket_name, is_dev)

    only_in_s3 = s3_files - db_files
    only_in_db = db_files - s3_files

    print('File presenti solo in S3:', only_in_s3)
    print('File presenti solo nel DB:', only_in_db)
