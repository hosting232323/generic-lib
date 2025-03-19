import os
import boto3
import botocore
from flask import abort
from dotenv import load_dotenv

load_dotenv()

s3 = None
ALLOWED_EXTENSIONS = ['png', 'jpg', 'jpeg', 'gif', 'pdf', 'txt', 'doc', 'docx']

if 'AWS_ACCESS_KEY_ID' in os.environ and 'AWS_SECRET_ACCESS_KEY' in os.environ:
  s3 = boto3.client(
    's3',
    aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'],
  )

def storage_decorator(func):
  def wrapper(bucket_name: str, key: str, *args, **kwargs):
    if '.' in key:
      extension = key.split('.')[-1]
      if not extension in ALLOWED_EXTENSIONS:
        return {'status': 'ko', 'error': 'Invalid file extension'}
    else:
      return {
        'status': 'ko',
        'error': 'File name does not contain an extension'
      }
    return func(bucket_name, key, *args, **kwargs)
  return wrapper

def get_s3_key(key, is_dev):
  if is_dev is None:
    return key 
  elif is_dev:
    return f"test/{key}"
  else:
    return f"prod/{key}"  

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

def upload_file_to_s3(file, bucket_name, key, is_dev=None):
  key = get_s3_key(key, is_dev)
  s3.upload_fileobj(file, bucket_name, key)

def list_files_in_s3(bucket, folder='', is_dev=None):
  folder = get_s3_key(folder, is_dev) if folder else get_s3_key('', is_dev)
  return [obj['Key'] for obj in s3.list_objects_v2(Bucket=bucket, Prefix=folder)['Contents']]
