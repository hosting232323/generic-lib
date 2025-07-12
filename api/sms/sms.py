import traceback
import requests

def send_sms(api_key: str, api_secret: str, sender: str, addressee: str, text: str) -> dict:

  try:
    if not api_key or not api_secret:
      return {
        "status": "ko",
        "message": "API key and Secret are required"
      }

    if not sender or not addressee or not text:
      return {
        "status": "ko",
        "message": "Sender, to number, and text message are required"
      }

    headers = {'Content-Type': 'application/x-www-form-urlencoded'}

    payload = {
      'api_key': api_key,
      'api_secret': api_secret,
      'from': sender,
      'to': addressee,
      'text': text
    }

    response = requests.post('https://rest.nexmo.com/sms/json', headers=headers, data=payload)

    if response.status_code != 200:
      return {
        "status": "ko",
        "message": "Failed to send SMS"
      }

    return {
      "status": "ok",
      "data": response.json()
    }
  except Exception as e:
    traceback.print_exc()
    return {'status': 'ko', 'message': str(e)}