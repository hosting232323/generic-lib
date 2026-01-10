import boto3
import botocore
from flask import abort

from ..settings import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, IS_DEV


S3 = None

if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
  S3 = boto3.client('s3', aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY)


def storage_decorator(func):
  def wrapper(*args, **kwargs):
    if not S3:
      raise ValueError('Api Key S3 non configurate')

    return func(*args, **kwargs)

  wrapper.__name__ = func.__name__
  return wrapper


@storage_decorator
def download_file_from_s3(bucket_name, key):
  key = get_s3_key(key)
  try:
    return S3.get_object(Bucket=bucket_name, Key=str(key))['Body'].read()
  except botocore.exceptions.ClientError as e:
    if e.response['Error']['Code'] == 'NoSuchKey':
      raise abort(404)
    else:
      raise e


@storage_decorator
def delete_file_from_s3(filename, folder, subfolder=None):
  if subfolder:
    key = f'{subfolder}/{filename}'
  else:
    key = get_s3_key(filename)
  S3.delete_object(Bucket=folder, Key=key)


@storage_decorator
def upload_file_to_s3(content, filename, folder, subfolder=None):
  if subfolder:
    key = f'{subfolder}/{filename}'
  else:
    key = get_s3_key(filename)
  S3.upload_fileobj(content, folder, key)
  return f'https://{folder}.s3.eu-north-1.amazonaws.com/{key}'


@storage_decorator
def list_files_in_s3(folder, subfolder=None):
  if subfolder:
    key = subfolder
  else:
    key = get_s3_key('')
    
  files = []
  continuation_token = None
  while True:
    list_params = {'Bucket': folder, 'Prefix': key}
    if continuation_token:
      list_params['ContinuationToken'] = continuation_token

    response = S3.list_objects_v2(**list_params)
    if 'Contents' in response:
      files.extend(obj['Key'] for obj in response['Contents'])
    if response.get('IsTruncated'):
      continuation_token = response['NextContinuationToken']
    else:
      break
  return files


def get_s3_key(key):
  if IS_DEV is None:
    return key
  elif IS_DEV:
    return f'test/{key}'
  else:
    return f'prod/{key}'
