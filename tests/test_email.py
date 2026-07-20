import pytest
from unittest.mock import patch
from api.email import send_email


@patch('api.email._deliver')
@patch('time.sleep')
@patch('api.email.send_telegram_message')
@patch.dict('api.email.sender.EMAIL_SENDER', {
    'name': 'Sender Name',
    'address': 'sender@example.com',
    'login': 'sender@example.com',
    'password': 'secretpassword'
})
def test_send_email_error_sends_telegram_message(mock_send_telegram, mock_sleep, mock_deliver):
  # Configure _deliver to raise an exception every time
  mock_deliver.side_effect = Exception("SMTP Connection Timeout / Brevo Error")

  # Call send_email
  result = send_email("test@example.com", "Test body", "Test Subject")

  # Verify send_email returns False
  assert result is False

  # Verify _deliver was called 3 times (the maximum number of retries)
  assert mock_deliver.call_count == 3

  # Verify time.sleep was called 2 times (after attempt 1 and 2, but not after attempt 3)
  assert mock_sleep.call_count == 2
  mock_sleep.assert_any_call(2.0)  # attempt 1 backoff: 2.0 * 1
  mock_sleep.assert_any_call(4.0)  # attempt 2 backoff: 2.0 * 2

  # Verify send_telegram_message was called once
  mock_send_telegram.assert_called_once()
  
  # Check that the telegram message contains the error details
  telegram_text = mock_send_telegram.call_args[0][0]
  assert "❌ *Errore invio mail a* `test@example.com`" in telegram_text
  assert "*Subject:* Test Subject" in telegram_text
  assert "SMTP Connection Timeout / Brevo Error" in telegram_text
