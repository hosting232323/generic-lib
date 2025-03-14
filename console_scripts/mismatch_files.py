import psycopg2
import os
import boto3

def get_user_input():
    db_url = input('Inserisci l\'URL del database: ')
    query = input('Inserisci la query per ottenere i file: ')
    bucket_name = input('Inserisci il nome del bucket S3: ')
    aws_access_key_id = input('Inserisci l\'AWS Access Key ID: ')
    aws_secret_access_key = input('Inserisci l\'AWS Secret Access Key: ')

    return db_url, query, bucket_name, aws_access_key_id, aws_secret_access_key

def get_db_files(db_url, query):
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        cursor.execute(query)
        urls = {row[0] for row in cursor.fetchall()}
        conn.close()

        return {os.path.basename(url) for url in urls}
    except Exception as e:
        print(f"Errore nel recupero dei file dal database: {e}")
        return set()

def get_s3_files(bucket_name, aws_access_key_id, aws_secret_access_key):
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key
        )

        response = s3_client.list_objects_v2(Bucket=bucket_name)
        return {os.path.basename(obj['Key']) for obj in response.get('Contents', [])}
    except Exception as e:
        print(f"Errore nel recupero dei file da S3: {e}")
        return set()

def run_comparison():
    db_url, query, bucket_name, aws_access_key_id, aws_secret_access_key = get_user_input()

    db_files = get_db_files(db_url, query)
    s3_files = get_s3_files(bucket_name, aws_access_key_id, aws_secret_access_key)

    only_in_s3 = s3_files - db_files
    only_in_db = db_files - s3_files

    print('File presenti solo in S3:', only_in_s3)
    print()
    print('File presenti solo nel DB:', only_in_db)