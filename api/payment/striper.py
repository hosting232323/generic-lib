import stripe
import traceback
from .utils import setup_stripe_products


def create_stripe_session_(settings, request):
  try:
    return stripe.checkout.Session.create(
      payment_method_types=['card'],
      line_items=setup_stripe_products(request.json),
      mode='payment',
      success_url=settings['url']['success_url'],
      cancel_url=settings['url']['cancel_url'],
      shipping_address_collection={'allowed_countries': ['IT']}
    )
  except stripe.error.StripeError as e:
    traceback.print_exc()
    return {'status': 'ko', 'message': str(e)}
  except Exception as e:
    traceback.print_exc()
    return {'status': 'ko', 'message': 'Qualcosa è andato storto'}
