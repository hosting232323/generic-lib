from dotenv import load_dotenv
import stripe
import uuid
import time

load_dotenv()

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
    raise e

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