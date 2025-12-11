import boto3
import botocore
from flask import abort

from api.settings import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY


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
def download_file_from_s3(bucket_name, key, is_dev=None):
  key = get_s3_key(key, is_dev)
  try:
    return S3.get_object(Bucket=bucket_name, Key=str(key))['Body'].read()
  except botocore.exceptions.ClientError as e:
    if e.response['Error']['Code'] == 'NoSuchKey':
      raise abort(404)
    else:
      raise e


@storage_decorator
def delete_file_from_s3(bucket_name, key, is_dev=None):
  key = get_s3_key(key, is_dev)
  S3.delete_object(Bucket=bucket_name, Key=key)


@storage_decorator
def upload_file_to_s3(file, bucket_name, key, allowed_extension=None, is_dev=None):
  key = get_s3_key(key, is_dev)
  if allowed_extension:
    check = extension_allowed(key, allowed_extension)
    if check['status'] == 'ko':
      raise ValueError(check['error'])

  S3.upload_fileobj(file, bucket_name, key)


@storage_decorator
def list_files_in_s3(bucket, folder=''):
  files = []
  continuation_token = None
  while True:
    list_params = {'Bucket': bucket, 'Prefix': folder}
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


def upload_file_to_s3(content, filename, bucket_name, allowed_extension=None, is_dev=None):
  key = get_s3_key(filename, is_dev)
  if allowed_extension:
    check = extension_allowed(key, allowed_extension)
    if check['status'] == 'ko':
      raise ValueError(check['error'])

  S3.upload_fileobj(content, bucket_name, key)


def delete_file_from_s3(key, bucket_name, is_dev=None):
  key = get_s3_key(key, is_dev)
  S3.delete_object(Bucket=bucket_name, Key=key)


def list_files_in_s3(bucket, folder=''):
  files = []
  continuation_token = None
  while True:
    list_params = {'Bucket': bucket, 'Prefix': folder}
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


def download_file_from_s3(bucket_name, key, is_dev=None):
  key = get_s3_key(key, is_dev)
  try:
    return S3.get_object(Bucket=bucket_name, Key=str(key))['Body'].read()
  except botocore.exceptions.ClientError as e:
    if e.response['Error']['Code'] == 'NoSuchKey':
      raise abort(404)
    else:
      raise e


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
