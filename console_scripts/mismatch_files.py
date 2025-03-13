import json
import boto3
import psycopg2
from typing import Set
import os
def get_db_files(db_url: str, query: str) -> Set[str]:
    """Recupera i nomi dei file dal database PostgreSQL."""
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        cursor.execute(query)
        urls = {row[0] for row in cursor.fetchall()}
        files = {os.path.basename(url) for url in urls}
        
        conn.close()
        return files
    except Exception as e:
        print(f"Errore nel recupero dei file dal database: {e}")
        return set()

def get_s3_files(bucket_name: str, aws_access_key_id: str, aws_secret_access_key: str) -> Set[str]:
    """Recupera i nomi dei file dal bucket S3."""
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key
        )
        response = s3_client.list_objects_v2(Bucket=bucket_name)
        return {obj["Key"] for obj in response.get("Contents", [])} if "Contents" in response else set()
    except Exception as e:
        print(f"Errore nel recupero dei file da S3: {e}")
        return set()

def check_mismatches(db_files: Set[str], s3_files: Set[str]):
    """Confronta i file tra DB e S3."""
    only_in_db = db_files - s3_files
    only_in_s3 = s3_files - db_files

    return {
        "only_in_db": list(only_in_db),
        "only_in_s3": list(only_in_s3),
    }