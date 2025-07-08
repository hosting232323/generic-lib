from dataclasses import dataclass
from typing import Union

@dataclass
class PaymentRequest:
  mode: str
  stripe_api_key: str
  url: dict
  line_items: list
  customer_email: Union[None, str] = None
  shipping_address_collection: Union[None, dict] = None

  def __post_init__(self):
    """Validate the PaymentRequest object"""
    if self.mode not in ["payment", "subscription"]:
      raise ValueError("mode must be either 'payment' or 'subscription'")
    
    if not self.stripe_api_key:
      raise ValueError("stripe_api_key is required")
    
    if self.mode == "subscription" and not self.customer_email:
      raise ValueError("customer_email is required")
    
    if self.line_items is None or not isinstance(self.line_items, list):
      raise ValueError("line_items must be a list and is required")
    
    for item in self.line_items:
      if not isinstance(item, dict):
        raise ValueError("Each item in line_items must be a dictionary")
    # example line_items for subscription 
    # line_items = [{"price": "{price_id}", "quantity": 1}]
    # example line_items for payment
    # line_items = [{"price_data": {"currency": "eur", "product_data": {"name": "My Product"}, "unit_amount": 1000}, "quantity": 1}]
    
    if self.shipping_address_collection is not None and not isinstance(self.shipping_address_collection, dict):
      raise ValueError("shipping_address_collection must be a dictionary or None")
    
    """Validate that url contains required success_url and cancel_url"""
    if not self.url:
        raise ValueError("url dictionary is required")
    
    if "success_url" not in self.url:
        raise ValueError("success_url is required in url dictionary")
        
    if "cancel_url" not in self.url:
        raise ValueError("cancel_url is required in url dictionary")
