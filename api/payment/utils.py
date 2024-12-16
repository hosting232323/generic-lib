import os
import json


def setup_stripe_products(products: list):
  stripe_products = []
  for product in products:
    for element in read_products_():
      if product['product'] == element['id']:
        stripe_products.append(
          {
            'quantity': product['quantity'],
            'price_data': {
              'currency': 'eur',
              'unit_amount': element['price'],
              'product_data': {'name': element['name']}
            }
          }
        )
  return stripe_products


def read_settings_(settings_path: str):
  with open(settings_path, 'r') as file:
    return json.load(file)


def read_products_(products_path: str):
  with open(products_path, 'r') as file:
    return json.load(file)


def _check_exists(path):
  return os.path.exists(path)
