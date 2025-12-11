import os
import boto3
import botocore
from flask import abort
from datetime import datetime
from dotenv import load_dotenv
from werkzeug.utils import secure_filename


load_dotenv()

s3 = None

if 'AWS_ACCESS_KEY_ID' in os.environ and 'AWS_SECRET_ACCESS_KEY' in os.environ:
  s3 = boto3.client(
    's3',
    aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'],
  )


def extension_allowed(key: str, allowed_extension: list[str]):
  if '.' in key:
    extension = key.split('.')[-1]
    if extension not in allowed_extension:
      return {'status': 'ko', 'error': 'Invalid file extension'}
  else:
    return {'status': 'ko', 'error': 'File name does not contain an extension'}

  return {'status': 'ok'}


def get_s3_key(key, is_dev):
  if is_dev is None:
    return key
  elif is_dev:
    return f'test/{key}'
  else:
    return f'prod/{key}'


def download_file_from_s3(bucket_name, key, is_dev=None):
  key = get_s3_key(key, is_dev)
  try:
    return s3.get_object(Bucket=bucket_name, Key=str(key))['Body'].read()
  except botocore.exceptions.ClientError as e:
    if e.response['Error']['Code'] == 'NoSuchKey':
      raise abort(404)
    else:
      raise e


def delete_file_from_s3(bucket_name, key, is_dev=None):
  key = get_s3_key(key, is_dev)
  s3.delete_object(Bucket=bucket_name, Key=key)


def upload_file_to_s3(file, bucket_name, key, allowed_extension=None, is_dev=None):
  key = get_s3_key(key, is_dev)
  if allowed_extension:
    check = extension_allowed(key, allowed_extension)
    if check['status'] == 'ko':
      raise ValueError(check['error'])

  s3.upload_fileobj(file, bucket_name, key)


def list_files_in_s3(bucket, folder=''):
  files = []
  continuation_token = None
  while True:
    list_params = {'Bucket': bucket, 'Prefix': folder}
    if continuation_token:
      list_params['ContinuationToken'] = continuation_token

    response = s3.list_objects_v2(**list_params)
    if 'Contents' in response:
      files.extend(obj['Key'] for obj in response['Contents'])
    if response.get('IsTruncated'):
      continuation_token = response['NextContinuationToken']
    else:
      break
  return files


def db_backup_s3(zip_filename: str, sub_folder):
  s3_bucket = 'fastsite-postgres-backup'
  s3_key = f'{sub_folder}/{secure_filename(zip_filename)}'

  with open(zip_filename, 'rb') as file:
    upload_file_to_s3(file, s3_bucket, s3_key)
  os.remove(zip_filename)
  manage_s3_backups(s3_bucket, sub_folder)

  print(f'[{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}] Backup eseguito!')


def db_backup_local(zip_filename: str, folder):
  safe_name = secure_filename(zip_filename)
  
  os.makedirs(folder, exist_ok=True)
  dest_path = os.path.join(folder, safe_name)

  os.rename(zip_filename, dest_path)
  manage_local_backups(folder)
  
  print(f'[{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}] Backup eseguito!')


def manage_local_backups(local_folder: str):
  backups = [
    os.path.join(local_folder, f)
    for f in os.listdir(local_folder)
    if os.path.isfile(os.path.join(local_folder, f))
  ]
    
  backups.sort()
    
  backup_days = int(os.environ.get('POSTGRES_BACKUP_DAYS', 14))

  if len(backups) > backup_days:
    files_to_delete = backups[: len(backups) - backup_days]
    for path in files_to_delete:
      os.remove(path)


def manage_s3_backups(bucket: str, sub_folder: str):
  backups = list_files_in_s3(bucket, sub_folder)
  backups.sort()
  backup_days = int(os.environ.get('POSTGRES_BACKUP_DAYS', 14))

  if len(backups) > backup_days:
    files_to_delete = backups[: len(backups) - backup_days]
    for file_key in files_to_delete:
      delete_file_from_s3(bucket, file_key)
