import os
import boto3
import botocore
from flask import abort
from dotenv import load_dotenv


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
    if not extension in allowed_extension:
      return {'status': 'ko', 'error': 'Invalid file extension'}
  else:
    return {
      'status': 'ko',
      'error': 'File name does not contain an extension'
    }
    
  return {'status': 'ok'}


def download_file_from_s3(bucket_name, key):
  try:
    return s3.get_object(Bucket=bucket_name, Key=str(key))['Body'].read()
  except botocore.exceptions.ClientError as e:
    if e.response['Error']['Code'] == 'NoSuchKey':
      raise abort(404)
    else:
      raise e


def delete_file_from_s3(bucket_name, key):
  s3.delete_object(Bucket=bucket_name, Key=key)


def upload_file_to_s3(file, bucket_name, key, allowed_extension = None):
  if allowed_extension:
    check = extension_allowed(key, allowed_extension)
    if check['status'] == 'ko':
      raise ValueError(check['error'])

  s3.upload_fileobj(file, bucket_name, key)


def list_files_in_s3(bucket, folder='', is_dev=None):
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
