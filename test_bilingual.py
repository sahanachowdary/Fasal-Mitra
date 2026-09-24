"""Offline contract and security checks. All provider operations are mocked."""
import json
import secrets
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from xml.etree import ElementTree as ET

import bilingual_common as common
import bilingual_server as server
from twilio.request_validator import RequestValidator

class ImmediatePool:
    def submit(self, fn, *args):
        fn(*args)

class DemoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = {
            'TWILIO_ACCOUNT_SID': 'AC' + '1' * 32,
            'TWILIO_AUTH_TOKEN': 'test-secret-never-real',
            'TWILIO_VOICE_FROM': '+15555550100',
            'TWILIO_SMS_FROM': '+15555550100',
            'ALLOWED_TEST_NUMBERS': '+919000000000',
            'PUBLIC_BASE_URL': 'https://example.ngrok-free.dev',
            'GEMINI_API_KEY': 'fake-test-key', 'GEMINI_MODEL': 'gemini-2.5-flash-lite',
            'DEMO_SMS_ENABLED': '0'}
        self.patches = [patch.object(common, 'DB_PATH', Path(self.tmp.name) / 'calls.db'),
                        patch.object(common, 'config', lambda: self.settings),
                        patch.object(server, 'config', lambda: self.settings),
                        patch.object(server, 'pool', ImmediatePool())]
        for p in self.patches:
            p.start()
        common.init_db()
        self.token = secrets.token_urlsafe(32)
        self.digest = common.token_hash(self.token)
        self.sid = 'CA' + '2' * 32
        self.form = {'CallSid': self.sid, 'AccountSid': self.settings['TWILIO_ACCOUNT_SID'],
                     'To': '+919000000000', 'Direction': 'outbound-api'}
        with common.database() as con:
            con.execute('INSERT INTO demo_calls(token_hash,sid,phone,created,expires,mode) VALUES(?,?,?,?,?,?)',
                        (self.digest, self.sid, self.form['To'], time.time(), time.time()+300, 'ai'))
        self.web = server.app.test_client()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def post(self, path, extra=None, **kwargs):
        response = self.web.post(path + '?k=' + self.token, data={**self.form, **(extra or {})}, **kwargs)
        if path == '/demo/voice' and response.status_code == 200 and server.read(self.digest)['stage'] == 'language':
            return self.web.post('/demo/language?k=' + self.token, data={**self.form, 'Digits':'1'})
        return response

    def test_unsigned_request_needs_unexpired_sid_bound_token(self):
        self.assertEqual(self.web.post('/demo/voice', data=self.form).status_code, 403)
        self.assertEqual(self.post('/demo/voice', {'CallSid': 'CA'+'3'*32}).status_code, 403)
        self.assertEqual(self.post('/demo/voice', {'AccountSid': 'AC'+'3'*32}).status_code, 403)
        self.assertEqual(self.post('/demo/voice', {'To': '+919999999999'}).status_code, 403)
        server.update(self.digest, expires=time.time()-1)
        self.assertEqual(self.post('/demo/voice').status_code, 403)

    def test_forged_token_and_wrong_present_signature_rejected(self):
        forged = self.web.post('/demo/voice?k=' + secrets.token_urlsafe(32), data=self.form)
        self.assertEqual(forged.status_code, 403)
        self.assertEqual(self.post('/demo/voice', headers={'X-Twilio-Signature': 'wrong'}).status_code, 403)

    def test_valid_signature_with_token(self):
        url = self.settings['PUBLIC_BASE_URL'] + '/demo/voice?k=' + self.token
        signature = RequestValidator(self.settings['TWILIO_AUTH_TOKEN']).compute_signature(url, self.form)
        self.assertEqual(self.post('/demo/voice', headers={'X-Twilio-Signature': signature}).status_code, 200)

    def test_welcome_does_not_invoke_ai(self):
        server.update(self.digest, mode='welcome')
        with patch.object(server, 'extract') as ai:
            response = self.post('/demo/voice')
        self.assertIn(b'connected to your laptop', response.data)
        ai.assert_not_called()
        self.assertEqual(server.read(self.digest)['stage'], 'done')
        self.assertEqual(self.post('/demo/voice').status_code, 403)

    def test_real_flow_shape_spoken_rice_confirm_and_recommendation(self):
        welcome = ET.fromstring(self.post('/demo/voice').data)
        self.assertEqual(welcome.find('Gather').get('input'), 'speech')
        self.assertIn('?k=', welcome.find('Gather').get('action'))
        with patch.object(server, 'extract', return_value={'crop': 'Rice', 'kg': 20}) as ai:
            capture = self.post('/demo/capture', {'SpeechResult': 'I harvested 20 kg of rice'})
        self.assertEqual(capture.status_code, 200)
        ai.assert_called_once()
        result = self.post('/demo/result')
        self.assertIn(b'20 kilograms of rice', result.data)
        self.assertIn(b'say yes or no', result.data)
        done = self.post('/demo/confirm', {'SpeechResult': 'Yes, correct.'})
        self.assertIn(b'Demo Local Buyer', done.data)
        self.assertIn(b'600 rupees', done.data)
        self.assertIn(b'not live prices', done.data)

    def test_no_confirmation_does_not_recommend(self):
        server.update(self.digest, stage='confirm', fields=json.dumps({'crop':'Rice','kg':20}))
        response = self.post('/demo/confirm', {'SpeechResult': 'No, that is not correct'})
        self.assertNotIn(b'Demo Local Buyer', response.data)
        self.assertIn(b'unconfirmed', response.data)

    def test_missing_weight_followup_and_bounded_silence(self):
        self.post('/demo/voice')
        with patch.object(server, 'extract', return_value={'crop':'Paddy','kg':None}):
            self.post('/demo/capture', {'SpeechResult':'paddy in bags'})
        self.assertIn(b'How many kilograms', self.post('/demo/result').data)
        with patch.object(server, 'extract') as ai:
            self.post('/demo/capture', {'SpeechResult':''})
            stopped = self.post('/demo/capture', {'SpeechResult':''})
            ai.assert_not_called()
        self.assertIn(b'could not get both details', stopped.data)

    def test_processing_callbacks_return_quickly_without_new_ai(self):
        server.update(self.digest, stage='processing', started=time.time())
        with patch.object(server, 'extract') as ai:
            response = self.post('/demo/result')
            duplicate = self.post('/demo/capture', {'SpeechResult':'rice 20 kg'})
        ai.assert_not_called()
        self.assertIsNotNone(ET.fromstring(response.data).find('Pause'))
        self.assertIsNotNone(ET.fromstring(duplicate.data).find('Redirect'))

    def test_job_timeout_and_callback_budget_end(self):
        server.update(self.digest, stage='processing', started=time.time()-40)
        self.assertIn(b'taking too long', self.post('/demo/result').data)
        server.update(self.digest, stage='processing', expires=time.time()+300, hops=8)
        self.assertIn(b'step limit', self.post('/demo/result').data)

    def test_ai_failure_is_honest_no_fallback_fake_result(self):
        self.post('/demo/voice')
        with patch.object(server, 'extract', side_effect=common.AIError('Quota unavailable')):
            self.post('/demo/capture', {'SpeechResult':'rice 20 kg'})
        self.assertIn(b'No result was guessed', self.post('/demo/result').data)

    def test_provider_extraction_request_and_schema_validation(self):
        reply = Mock(ok=True, status_code=200)
        reply.json.return_value = {'candidates':[{'content':{'parts':[{'text':'{"crop":"Rice","kg":20}'}]}}]}
        with patch.object(common.requests, 'post', return_value=reply) as post:
            self.assertEqual(common.extract('rice 20 kg'), {'crop':'Rice','kg':20})
        sent = post.call_args.kwargs
        self.assertEqual(sent['headers'], {'x-goog-api-key':'fake-test-key'})
        self.assertNotIn(self.form['To'], json.dumps(sent['json']))
        reply.json.return_value = {'candidates':[{'content':{'parts':[{'text':'{"crop":"Rice","kg":-20}'}]}}]}
        with patch.object(common.requests, 'post', return_value=reply):
            self.assertIsNone(common.extract('rice')['kg'])

    def test_gemini_quota_message_without_key_leak(self):
        with patch.object(common.requests, 'post', return_value=Mock(status_code=429)):
            with self.assertRaisesRegex(common.AIError, 'quota'):
                common.extract('rice 20 kg')

    def test_matching_changes_with_quantity_and_crop(self):
        self.assertIn('Demo Local Buyer', common.recommend({'crop':'Rice','kg':20}))
        self.assertIn('6300 rupees', common.recommend({'crop':'Rice','kg':200}))
        self.assertIn('400 rupees', common.recommend({'crop':'Paddy','kg':20}))

    def test_sms_requires_consent_and_only_once(self):
        self.settings['DEMO_SMS_ENABLED'] = '1'
        server.update(self.digest, stage='confirm', fields=json.dumps({'crop':'Rice','kg':20}))
        mock_client = Mock()
        mock_client.messages.create.return_value = Mock(status='queued', sid='SM'+'3'*32)
        with patch.object(server, 'client', return_value=mock_client):
            response = self.post('/demo/confirm', {'SpeechResult':'yes'})
            mock_client.messages.create.assert_not_called()
            self.assertEqual(ET.fromstring(response.data).find('Gather').get('input'), 'dtmf')
            self.post('/demo/sms', {'Digits':'1'})
            self.post('/demo/sms', {'Digits':'1'})
            mock_client.messages.create.assert_called_once()
            self.assertEqual(server.read(self.digest)['sms_state'], 'queued')

    def menu(self):
        return self.web.post('/demo/voice?k='+self.token, data=self.form)

    def test_menu_has_both_languages_and_authenticated_action(self):
        root = ET.fromstring(self.menu().data)
        gather = root.find('Gather')
        self.assertEqual(gather.get('input'), 'dtmf')
        self.assertEqual(gather.get('numDigits'), '1')
        self.assertIn('/demo/language?k=', gather.get('action'))
        self.assertEqual([s.get('language') for s in gather.findall('Say')], ['en-US','te-IN'])
        self.assertEqual(self.web.post('/demo/language', data={**self.form,'Digits':'2'}).status_code,403)

    def test_telugu_end_to_end_mocked_ai(self):
        self.menu()
        response = self.post('/demo/language', {'Digits':'2'})
        gather = ET.fromstring(response.data).find('Gather')
        self.assertEqual(gather.get('language'),'te-IN')
        self.assertEqual(gather.get('speechModel'),'googlev2_short')
        self.assertEqual(gather.get('speechTimeout'),'2')
        self.assertIn('ఉల్లిపాయలు',response.get_data(as_text=True))
        with patch.object(server,'extract',return_value={'crop':'Onion','kg':50}) as ai:
            self.post('/demo/capture',{'SpeechResult':'నా దగ్గర యాభై కిలోల ఉల్లిపాయలు ఉన్నాయి'})
        self.assertIn('యాభై',ai.call_args.args[0])
        confirmation = self.post('/demo/result').get_data(as_text=True)
        self.assertIn('50 కిలోల ఉల్లిపాయలు',confirmation)
        self.assertIn('అవును లేదా కాదు',confirmation)
        done = ET.fromstring(self.post('/demo/confirm',{'SpeechResult':'అవును'}).data)
        self.assertEqual(done.find('Say').get('language'),'te-IN')
        self.assertIn('900 రూపాయలు',done.find('Say').text)
        self.assertIn('నిజమైన మార్కెట్ ధరలు లేదా బుకింగ్ కాదు',done.find('Say').text)
        self.assertEqual(server.read(self.digest)['stage'],'done')

    def test_telugu_negative_overrides_positive(self):
        server.update(self.digest,stage='confirm',language='te',fields=json.dumps({'crop':'Rice','kg':20}))
        done = self.post('/demo/confirm',{'SpeechResult':'అవును కాదు'})
        self.assertIn('నిర్ధారణ కాలేదు',done.get_data(as_text=True))
        self.assertNotIn('600',done.get_data(as_text=True))

    def test_invalid_language_and_silence_end_after_one_retry(self):
        self.menu()
        retry = self.post('/demo/language',{'Digits':'9'})
        self.assertIsNotNone(ET.fromstring(retry.data).find('Gather'))
        end = self.post('/demo/language',{'Digits':''})
        self.assertIsNotNone(ET.fromstring(end.data).find('Hangup'))
        self.assertIsNone(ET.fromstring(end.data).find('Gather'))
        self.assertEqual(server.read(self.digest)['stage'],'done')

    def test_language_cannot_change_after_selection(self):
        self.menu()
        self.post('/demo/language',{'Digits':'2'})
        self.post('/demo/language',{'Digits':'1'})
        self.assertEqual(server.read(self.digest)['language'],'te')
        self.assertEqual(server.read(self.digest)['stage'],'done')

    def test_telugu_missing_quantity_prompt(self):
        server.update(self.digest,stage='ready',language='te',fields=json.dumps({'crop':'Paddy','kg':None}))
        response = self.post('/demo/result')
        self.assertIn('ఎన్ని కిలోలు',response.get_data(as_text=True))
        self.assertEqual(ET.fromstring(response.data).find('Gather').get('language'),'te-IN')

    def test_telugu_error_and_budget_messages(self):
        server.update(self.digest,stage='ai_error',language='te')
        response=self.post('/demo/result').get_data(as_text=True)
        self.assertIn('ఊహించి ఫలితం ఇవ్వలేదు',response)
        server.update(self.digest,stage='processing',expires=time.time()+300,hops=8)
        self.assertIn('పరిమితి',self.post('/demo/result').get_data(as_text=True))

    def test_matching_same_amount_in_both_languages(self):
        for crop in common.SAMPLE_PRICES:
            for kg in (20,200,6000):
                en=common.recommend({'crop':crop,'kg':kg})
                te=common.recommend({'crop':crop,'kg':kg},'te')
                import re
                self.assertEqual(re.findall(r'[0-9]+',en),re.findall(r'[0-9]+',te))

if __name__ == '__main__':
    unittest.main()
