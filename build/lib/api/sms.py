import re
import requests
import traceback


def send_sms(api_key: str, api_secret: str, sender: str, addressee: str, text: str) -> dict:
  """
  Sends an SMS message using Vonage.

  Args:
    api_key (str): The API key for authentication with Vonage.
    api_secret (str): The API secret for authentication with Vonage.
    sender (str): The sender identifier (alphanumeric string, spaces allowed).
    addressee (str): The recipient's phone number (digits, spaces, hyphens, parentheses, plus sign allowed).
    text (str): The text message content to be sent.

  Returns:
    dict: A dictionary containing the operation status and result:
      - On success: {'status': 'ok', 'data': <response_json>}
      - On failure: {'status': 'ko', 'message': <error_message>}

  Raises:
    Exception: Any unexpected errors are caught and returned in the response dict.

  Example:
    >>> result = send_sms('your_api_key', 'your_secret', 'MyApp', '+1234567890', 'Hello World')
  """

  try:
    if not api_key or not api_secret:
      return {'status': 'ko', 'message': 'API key and Secret are required'}

    if not sender or not addressee or not text:
      return {'status': 'ko', 'message': 'Sender, addresse, and text message are required'}

    # validate sender is alphanumeric
    if not re.match(r'^[a-zA-Z0-9\s]+$', sender):
      return {'status': 'ko', 'message': 'Sender must be an alphanumeric string (spaces allowed)'}

    # validate addressee is a phone number (digits, spaces, hyphens, plus sign allowed)
    phone_pattern = r'^[\+]?[\d\s\-\(\)]+$'
    if not re.match(phone_pattern, addressee):
      return {'status': 'ko', 'message': 'Addressee must be a valid phone number'}

    headers = {'Content-Type': 'application/x-www-form-urlencoded'}

    payload = {'api_key': api_key, 'api_secret': api_secret, 'from': sender, 'to': addressee, 'text': text}

    response = requests.post('https://rest.nexmo.com/sms/json', headers=headers, data=payload)

    if response.status_code != 200:
      return {'status': 'ko', 'message': 'Failed to send SMS'}

    return {'status': 'ok', 'data': response.json()}
  except Exception as e:
    traceback.print_exc()
    return {'status': 'ko', 'message': str(e)}
