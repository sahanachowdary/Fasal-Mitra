import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock
from twilio.request_validator import RequestValidator
import voice_server as v

SID = 'CA' + 'a' * 32
PHONE = '+919000000001'
ENV = {'TWILIO_ACCOUNT_SID': 'AC' + 'b' * 32, 'TWILIO_AUTH_TOKEN': 'test-token',
       'PUBLIC_BASE_URL': 'https://example.test', 'ALLOWED_TEST_NUMBERS': PHONE,
       'TWILIO_SMS_FROM': '+15005550006', 'OPENAI_API_KEY': 'unit-test-only'}
FIELDS = {'crop': 'Tomato', 'kg': 200, 'temperature': 32, 'age': 1, 'radius': 15, 'baseline': 6}

class VoiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, ENV)
        self.env.start()
        self.db_patch = patch.object(v, 'DB_PATH', Path(self.temp.name) / 'calls.db')
        self.db_patch.start()
        v.app.config['TESTING'] = True
        self.client = v.app.test_client()
    def tearDown(self):
        self.db_patch.stop()
        self.env.stop()
        self.temp.cleanup()
    def post(self, path, **extra):
        form = {'AccountSid': ENV['TWILIO_ACCOUNT_SID'], 'CallSid': SID,
                'From': PHONE, 'To': '+15005550006', 'Direction': 'inbound'}
        form.update(extra)
        signature = RequestValidator(ENV['TWILIO_AUTH_TOKEN']).compute_signature('https://example.test' + path, form)
        return self.client.post(path, data=form, headers={'X-Twilio-Signature': signature})
    def begin(self):
        self.assertIn(b'AI assisted', self.post('/voice').data)
        self.post('/consent', Digits='1')
    def test_unsigned_request_rejected(self):
        self.assertEqual(self.client.post('/voice').status_code, 403)
    def test_wrong_account_rejected(self):
        self.assertEqual(self.post('/voice', AccountSid='AC' + 'c' * 32).status_code, 403)
    def test_allowlist(self):
        self.assertIn(b'registered team', self.post('/voice', From='+919000000002').data)
    def test_outbound_direction_uses_to(self):
        self.assertIn(b'AI assisted', self.post('/voice', From='+15005550006', To=PHONE, Direction='outbound-api').data)
    def test_no_processing_before_consent(self):
        self.post('/voice')
        with patch.object(v, 'extract') as ai:
            self.post('/harvest', SpeechResult='200kg tomato')
            ai.assert_not_called()
    def test_full_flow_and_single_sms(self):
        self.begin()
        with patch.object(v, 'extract', return_value=FIELDS):
            self.assertIn(b'200 kilograms', self.post('/harvest', SpeechResult='two hundred kilograms tomatoes').data)
        self.assertIn(b'3650', self.post('/confirm', Digits='1').data)
        provider = Mock()
        provider.messages.create.return_value = SimpleNamespace(sid='SM' + 'd'*32, status='queued')
        with patch.object(v, 'twilio_client', return_value=provider):
            self.assertIn(b'submitted', self.post('/sms-consent', Digits='1').data)
            self.post('/sms-consent', Digits='1')
            self.assertEqual(provider.messages.create.call_count, 1)
            self.assertEqual(provider.messages.create.call_args.kwargs['to'], PHONE)
        self.post('/sms-status', MessageSid='SM'+'d'*32, MessageStatus='delivered')
        self.post('/sms-status', MessageSid='SM'+'d'*32, MessageStatus='sent')
        with v.db() as con:
            self.assertEqual(con.execute('SELECT state FROM sms').fetchone()[0], 'delivered')
    def test_decline_sms(self):
        v.save(SID, PHONE, {'stage': 'sms_consent', 'summary': 'demo'})
        with patch.object(v, 'twilio_client') as provider:
            self.post('/sms-consent', Digits='2')
            provider.assert_not_called()
    def test_missing_fields_followup(self):
        self.begin()
        with patch.object(v, 'extract', return_value={**FIELDS, 'kg': None}):
            self.assertIn(b'How many kilograms', self.post('/harvest', SpeechResult='two bags tomatoes').data)
        self.assertEqual(v.load(SID)[1]['pending'], 'kg')
    def test_model_failure_does_not_invent(self):
        self.begin()
        with patch.object(v, 'extract', side_effect=TimeoutError):
            self.assertIn(b'could not process', self.post('/harvest', SpeechResult='tomato').data)
        self.assertEqual(v.load(SID)[1]['fields'], {})
    def test_sms_timeout_is_not_retried(self):
        provider = Mock()
        provider.messages.create.side_effect = TimeoutError()
        with patch.object(v, 'twilio_client', return_value=provider):
            self.assertEqual(v.send_summary_once(SID, PHONE, 'demo'), 'failed_or_unknown')
            self.assertEqual(v.send_summary_once(SID, PHONE, 'demo'), 'already_requested')
            self.assertEqual(provider.messages.create.call_count, 1)
    def test_actual_ai_request_schema_and_validation(self):
        import json
        fake = Mock()
        fake.responses.create.return_value = SimpleNamespace(output_text=json.dumps({**FIELDS, 'kg': -1}))
        with patch.object(v, 'OpenAI', return_value=fake):
            fields = v.extract('one bag', {'fields': {}})
        self.assertIsNone(fields['kg'])
        self.assertTrue(fake.responses.create.call_args.kwargs['text']['format']['strict'])
        self.assertFalse(fake.responses.create.call_args.kwargs['store'])

if __name__ == '__main__':
    unittest.main()
