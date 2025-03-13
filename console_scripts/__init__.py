from database_api import data_export, data_import
from.mismatch_files import check_mismatches,get_db_files,get_s3_files
import json

#FALLO COME CIN COUT DEI DATI E POI LO CHIAMI DA TERMINALE SEMPLICEMENTE 
def check_aws_mismatches():
  json_input = input("Forniscimi il JSON per il confronto tra il DB e il bucket S3:\n")
    
  try:
      data = json.loads(json_input)
      required_keys = {"db_url", "query", "bucket_name", "aws_access_key_id", "aws_secret_access_key"}

      if not required_keys.issubset(data.keys()):
          missing_keys = required_keys - data.keys()
          print(f"Errore: manca(mancano) la/le chiave/i: {missing_keys}")
      else:
          # Recupero file da DB e S3
          db_files = get_db_files(data["db_url"], data["query"])
          s3_files = get_s3_files(data["bucket_name"], data["aws_access_key_id"], data["aws_secret_access_key"])
          print("\ndb files:", db_files)
          print("\ns3 files:", s3_files)
          # Confronto
          mismatches = check_mismatches(db_files, s3_files)

          # Stampa il risultato
          print("\nDifferenze tra DB e S3:")
          print(json.dumps(mismatches))
  
  except json.JSONDecodeError:
      print("Errore: il JSON fornito non è valido.")

def db_export():
  data_export()


def db_import():
  data_import()
