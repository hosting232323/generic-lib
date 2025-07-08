import stripe
import traceback
from .schemas import PaymentRequest
  
def create_stripe_session_(params: PaymentRequest):
  try:
    stripe.api_key = params.stripe_api_key

    customer_id = None
    
    # check if the user already exists in stripe customers
    if params.customer_email is not None:
      customers = stripe.Customer.list(email=params.customer_email).data

      if customers:
        customer_id = customers[0].id  # get the first customer id
      else:
        # create a new customer if not exist
        customer = stripe.Customer.create(email=params.customer_email)
        customer_id = customer.id

    session_params = {
      "payment_method_types": ["card"],
      "mode": params.mode,
      "line_items": params.line_items,
      "success_url": params.url['success_url'],
      "cancel_url": params.url['cancel_url']
    }

    if customer_id is not None:
      session_params["customer"] = customer_id
    
    if params.shipping_address_collection:
      session_params["shipping_address_collection"] = params.shipping_address_collection

    session = stripe.checkout.Session.create(**session_params)

    return {
      "status": "ok", 
      "checkout_url": session.url,
      "session_id": session.id
    }
  except stripe.error.StripeError as e:
    traceback.print_exc()
    return {'status': 'ko', 'message': str(e)}
  except Exception as e:
    traceback.print_exc()
    return {'status': 'ko', 'message': 'Qualcosa è andato storto'}

def stripe_webhook(payload, sig_header, webhook_secret):
  event = None

  try:
    event = stripe.Webhook.construct_event(
      payload, sig_header, webhook_secret
    )

    if event["type"] is not "invoice.paid" or event["type"] is not "invoice.payment_succeeded":
      return {
        "status": "ko",
        "message": "Event type not handled"
      }

    return {
      "status": "ok",
      "event": event["type"],
      "metadata": event["data"]["object"]
    }
  except ValueError as e:
    raise e
  except stripe.error.SignatureVerificationError as e:
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