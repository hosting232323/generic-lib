from database_api import data_export, data_import
from.mismatch_files import run_comparison
import json

#FALLO COME CIN COUT DEI DATI E POI LO CHIAMI DA TERMINALE SEMPLICEMENTE 
def check_aws_mismatches():
 run_comparison()

def db_export():
  data_export()


def db_import():
  data_import()
