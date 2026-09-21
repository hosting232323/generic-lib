import base64
from unittest.mock import patch
from api.email import send_email, _build_payload


EMAIL_SENDER_PATCH = patch.dict(
  'api.email.sender.EMAIL_SENDER',
  {'name': 'Sender Name', 'address': 'sender@example.com'},
)


@patch('api.email._deliver')
@patch('time.sleep')
@patch('api.email.send_telegram_message')
@EMAIL_SENDER_PATCH
def test_send_email_error_sends_telegram_message(mock_send_telegram, mock_sleep, mock_deliver):
  mock_deliver.side_effect = Exception('Resend API Error 500')

  result = send_email('test@example.com', 'Test body', 'Test Subject')

  assert result is None
  assert mock_deliver.call_count == 3
  assert mock_sleep.call_count == 2
  mock_sleep.assert_any_call(2.0)
  mock_sleep.assert_any_call(4.0)
  mock_send_telegram.assert_called_once()

  telegram_text = mock_send_telegram.call_args[0][0]
  assert '❌ *Errore invio mail a* `test@example.com`' in telegram_text
  assert '*Subject:* Test Subject' in telegram_text
  assert 'Resend API Error 500' in telegram_text
  assert 'Test body' in telegram_text


@patch('api.email._deliver')
@EMAIL_SENDER_PATCH
def test_send_email_success(mock_deliver):
  mock_deliver.return_value = 'email_id_12345'

  result = send_email('test@example.com', 'Test body', 'Test Subject')

  assert result == 'email_id_12345'
  mock_deliver.assert_called_once()


@EMAIL_SENDER_PATCH
def test_email_signature_appending():
  # 1. Test with dict signature
  body_dict = {'text': 'Hello world', 'html': '<h1>Hello world</h1>'}
  sig_dict = {'text': 'Text Signature', 'html': '<p>HTML Signature</p>'}
  payload = _build_payload('test@example.com', body_dict, 'Test Subject', signature=sig_dict)

  assert 'Hello world\n\nText Signature' in payload['text']
  assert '<h1>Hello world</h1><br><br><p>HTML Signature</p>' in payload['html']
  assert payload['from'] == 'Sender Name <sender@example.com>'
  assert payload['to'] == ['test@example.com']

  # 2. Test with string signature
  body_str = 'Hello world'
  payload_str = _build_payload('test@example.com', body_str, 'Test Subject', signature='Text Signature')
  assert 'Hello world\n\nText Signature' in payload_str['text']

  # 3. Test with no signature
  payload_no_sig = _build_payload('test@example.com', 'Hello world', 'Test Subject', signature=None)
  assert payload_no_sig['text'] == 'Hello world'


@EMAIL_SENDER_PATCH
def test_build_payload_attachments():
  attachments = [
    {'content': b'%PDF-', 'filename': 'doc.pdf'},
    {'content': b'image-bytes', 'filename': 'pic.png', 'content_type': 'image/png'},
    {'content': 'already-string', 'filename': 'test.txt'},
  ]
  payload = _build_payload('test@example.com', 'Body', 'Subject', attachments=attachments)

  assert len(payload['attachments']) == 3
  assert payload['attachments'][0]['filename'] == 'doc.pdf'
  assert payload['attachments'][0]['content'] == base64.b64encode(b'%PDF-').decode('ascii')
  assert 'content_type' not in payload['attachments'][0]

  assert payload['attachments'][1]['filename'] == 'pic.png'
  assert payload['attachments'][1]['content'] == base64.b64encode(b'image-bytes').decode('ascii')
  assert payload['attachments'][1]['content_type'] == 'image/png'

  assert payload['attachments'][2]['content'] == 'already-string'


@EMAIL_SENDER_PATCH
def test_build_payload_tags():
  payload = _build_payload('test@example.com', 'Body', 'Subject', tag='order_123!test')
  assert payload['tags'] == [{'name': 'tag', 'value': 'order-123-test'}]

  payload_none = _build_payload('test@example.com', 'Body', 'Subject', tag=None)
  assert 'tags' not in payload_none
