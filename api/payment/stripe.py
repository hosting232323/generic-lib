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

    # Validate and clean metadata
    validated_metadata = {}
    if params.metadata:
      for key, value in params.metadata.items():
        # Stripe metadata keys and values must be strings
        # and values cannot exceed 500 characters
        str_key = str(key)[:40]  # Limit key length
        str_value = str(value)[:500]  # Limit value length per Stripe requirements
        validated_metadata[str_key] = str_value

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
    
    # if is a subscription, we have to add subscription data and the inside metadata
    if params.mode == "subscription":
      session_params["subscription_data"] = {
        "metadata": validated_metadata
      }
    
    # if is a payment, we have to add metadata directly to the session
    if params.mode == "payment":
      session_params["metadata"] = validated_metadata

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

    if event["type"] not in ["invoice.paid", "invoice.payment_succeeded", "checkout.session.completed"]:
      return {
        "status": "ko",
        "message": "Event type not handled"
      }

    return {
      "status": "ok",
      "event": event["type"],
      "metadata": event["data"]["object"].to_dict()
    }
  except ValueError as e:
    raise e
  except stripe.error.SignatureVerificationError as e:
      raise e
  
def get_customer_data(filters):
  try:
    if not filters.get("stripe_api_key"):
      raise ValueError("Stripe API key is required")
    if not filters.get("customer_email"):
      raise ValueError("Customer email is required")

    stripe.api_key = filters.get("stripe_api_key")
    customers = stripe.Customer.list(email=filters.get("customer_email")).data

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

    if "base_info" in filters.get("params", {}):
      customer_data["base_info"] = {
        "id": customer.id,
        "email": customer.email,
        "name": customer.name,
        "phone": customer.phone,
        "address": customer.address
      }

    # subscriptions
    if "subscriptions" in filters.get("params", {}):
      customer_data["subscriptions"] = {}

      # get all subscriptions
      subscriptions = stripe.Subscription.list(customer=customer.id).data
      
      for subscription in subscriptions:
        project = subscription.metadata.get("project")
        
        if not project:
          continue
        
        # if a project filter is set, skip subscriptions not matching the project
        if filters.get("metadata") and filters.get("metadata").get("projects") and project not in filters.get("metadata").get("projects"):
          continue
        
        if project not in customer_data["subscriptions"]:
          customer_data["subscriptions"][project] = []
        
        customer_data["subscriptions"][project].append(subscription)

    # payments
    if "payments" in filters.get("params", {}):
      customer_data["payments"] = {}

      # get all payments
      payments = stripe.PaymentIntent.list(customer=customer.id).data

      for payment in payments:
        project = payment.metadata.get("project")
        
        if not project:
          continue
        
        # if a project filter is set, skip subscriptions not matching the project
        if filters.get("metadata") and filters.get("metadata").get("projects") and project not in filters.get("metadata").get("projects"):
          continue

        if project not in customer_data["payments"]:
          customer_data["payments"][project] = []

        customer_data["payments"][project].append(payment)

    return {
      "status": "ok",
      "customer": customer_data
    }
  except stripe.error.StripeError as e:
    raise e
  except Exception as e:
    raise e