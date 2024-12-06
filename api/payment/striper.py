import stripe
import traceback
from .utils import setup_stripe_products


def create_stripe_session_(settings, request):
    try:
        return stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=setup_stripe_products(request.json),
            mode="payment",
            success_url=settings["url"]["success_url"],
            cancel_url=settings["url"]["cancel_url"],
            shipping_address_collection={"allowed_countries": ["IT"]},
        )
    except stripe.error.StripeError as e:
        traceback.print_exc()
        return {"status": "ko", "message": str(e)}
    except Exception as e:
        traceback.print_exc()
        return {"status": "ko", "message": "Qualcosa è andato storto"}


# def handle_webhook(payload, received_sig):
#     try:
#         event = stripe.Webhook.construct_event(
#             payload,
#             received_sig,
#             stripe_keys["webhook_secret"]
#         )
#         data = event["data"]
#         return data
#     except ValueError:
#         return {"error": "Invalid payload"}
#     except Exception as e:
#         return {"error": str(e)}


# def process_payment_intent_succeeded(event):
#     session = stripe.checkout.Session.retrieve(
#         event["data"]["object"].id,
#         expand=["line_items"]
#     )
#     sale_info = []
#     for item in session.line_items.data:
#         sale_info.append(
#             {
#                 "quantity": item.quantity,
#                 "description": item.description,
#                 "amount_total": item.amount_total / 100,
#                 "currency": item.currency.upper(),
#             }
#         )
#     return sale_info
