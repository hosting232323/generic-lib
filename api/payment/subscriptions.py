import os
from dotenv import load_dotenv
import stripe
import uuid
import time

load_dotenv()

def create_subscription_stripe_session(stripe_api_key, customer_email, price_id, success_url, cancel_url):
  try:
    if not stripe_api_key:
      raise ValueError("Stripe API key is required")
    
    stripe.api_key = stripe_api_key
    if not customer_email or not price_id:
      raise ValueError("Email and Price ID are required")

    # check if the user already exists in stripe customers
    customers = stripe.Customer.list(email=customer_email).data

    if customers:
      customer_id = customers[0].id  # get the first customer id
    else:
      # create a new customer if not exist
      customer = stripe.Customer.create(email=customer_email)
      customer_id = customer.id

    session_params = {
      "payment_method_types": ["card"],
      "mode": "subscription",
      "customer": customer_id,
      "line_items": [{"price": price_id, "quantity": 1}],
      "success_url": success_url,
      "cancel_url": cancel_url
    }

    session = stripe.checkout.Session.create(**session_params)

    return {
      "status": "ok", 
      "checkout_url": session.url,
      "session_id": session.id
    }
  except stripe.error.StripeError as e:
    raise e

def create_subscription_webhook(stripe_api_key, payload, sig_header, webhook_secret):
  try:
    if not stripe_api_key:
      raise ValueError("Stripe API key is required")
    stripe.api_key = stripe
    # validate the webhook
    event = stripe.Webhook.construct_event(
      payload, sig_header, webhook_secret
    )

    return {
      "status": "ok", 
      "event": event
    }
  except (stripe.error.SignatureVerificationError) as e:
    raise ValueError(f"Invalid signature: {str(e)}")
  except stripe.error.StripeError as e:
    raise e
  except Exception as e:
    raise Exception(f"Webhook processing error: {str(e)}")

def report_subscription_usage(stripe_api_key, customer_id, usage_value, event_name):
  try:
    if not stripe_api_key:
      raise ValueError("Stripe API key is required")
    if not customer_id or not usage_value or not event_name:
      raise ValueError("Missing customer_id, usage_value or event_name")
    
    stripe.api_key = stripe_api_key
    
    # generate a unique identifier for idempotency. Stripe uses this to avoid duplicate events
    idempotency_key = str(uuid.uuid4())
    
    # register a metered event
    meter_event = stripe.billing.MeterEvent.create(
      event_name=event_name,
      timestamp=int(time.time()),
      identifier=idempotency_key,
      payload={
        "stripe_customer_id": customer_id,
        "value": str(usage_value),  # convert to string as required by Stripe
      }
    )
    
    return {
      "status": "ok", 
      "meter_event": meter_event
    }
  except stripe.error.StripeError as e:
    raise e
  except Exception as e:
    raise Exception(f"Usage reporting error: {str(e)}")

def delete_subscription(stripe_api_key, subscription_id):
  try:
    if not stripe_api_key:
      raise ValueError("Stripe API key is required")
    if not subscription_id:
      raise ValueError("Subscription ID is required")
      
    stripe.api_key = stripe_api_key
    deleted_subscription = stripe.Subscription.cancel(subscription_id)
    
    if deleted_subscription.status == 'canceled':
      return {
        "status": "ok",
        "message": "Subscription successfully canceled",
        "subscription": deleted_subscription
      }
    else:
      return {
        "status": "ko",
        "message": f"Failed to cancel subscription. Status: {deleted_subscription.status}"
      }
  except stripe.error.StripeError as e:
    raise e
  except Exception as e:
    raise e
  
def get_customer_data(stripe_api_key, customer_email, params=None):
  try:
    if not stripe_api_key:
      raise ValueError("Stripe API key is required")
    if not customer_email:
      raise ValueError("Customer email is required")
    if params is not None and not isinstance(params, list):
      raise ValueError("Params must be None or a list")
    
    stripe.api_key = stripe_api_key
    customers = stripe.Customer.list(email=customer_email).data
    
    # if there are no customers, return immediately
    if not customers:
      return {
        "status": "ko",
        "message": "Customer not found"
      }
    
    # if more than one customer is found, return an error
    if len(customers) > 1:
      return {
        "status": "ko",
        "message": "Multiple customers found with the same email"
      }
    
    customer = customers[0]
    # create object to store customer data
    customer_data = {}

    if params is None or "base_info" in params:
      customer_data["base_info"] = {
        "id": customer.id,
        "email": customer.email,
        "name": customer.name,
        "phone": customer.phone,
        "address": customer.address
      }

    if params is None or "subscriptions" in params:
      customer_data["subscriptions"] = []

      # get all subscriptions
      subscriptions = stripe.Subscription.list(customer=customer.id).data

      for subscription in subscriptions:
        customer_data["subscriptions"].append(subscription)

    if params is None or "payments" in params:
      customer_data["payments"] = []

      # get all payments
      payments = stripe.PaymentIntent.list(customer=customer.id).data

      for payment in payments:
        customer_data["payments"].append(payment)

    return {
      "status": "ok",
      "customer": customer_data
    }
  except stripe.error.StripeError as e:
    raise e
  except Exception as e:
    raise e