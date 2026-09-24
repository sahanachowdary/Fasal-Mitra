"""Outbound team demo only. A random, expiring per-call bearer token authenticates
callbacks and binds them to a locally initiated CallSid. This is NOT proof of a
Twilio signature. Never publish token URLs. Regular signatures are also validated
when present. Incoming calls and unsolicited webhooks are not supported.
"""
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from urllib.parse import urlencode

from flask import Flask, Response, abort, g, request
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import VoiceResponse, Gather
from demo_common import (AIError, allowed_numbers, base_url, client, config, database,
                         extract, init_db, recommend, required, token_hash)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16000
pool = ThreadPoolExecutor(max_workers=1)
# Access logs normally include query tokens. Keep them out of console output.
logging.getLogger('werkzeug').setLevel(logging.ERROR)

def update(digest, **values):
    with database() as con:
        con.execute('UPDATE demo_calls SET ' + ','.join(k + '=?' for k in values) + ' WHERE token_hash=?',
                    (*values.values(), digest))

def read(digest):
    with database() as con:
        row = con.execute('SELECT * FROM demo_calls WHERE token_hash=?', (digest,)).fetchone()
    return dict(row) if row else None

def authenticated(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = request.args.get('k', '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            abort(403, description='Missing demo call credential. Start calls with demo_call.py.')
        digest = token_hash(token)
        entry = read(digest)
        if (not entry or entry['expires'] < time.time() or not entry['sid']
                or entry['stage'] in ('done', 'failed')):
            abort(403, description='Demo call expired or not registered.')
        if (request.form.get('CallSid') != entry['sid']
                or request.form.get('AccountSid') != required('TWILIO_ACCOUNT_SID')
                or entry['phone'] not in allowed_numbers()):
            abort(403, description='Demo call identity mismatch.')
        # Only callbacks for the pre-authorized outbound call are accepted.
        if request.form.get('To') and request.form['To'] != entry['phone']:
            abort(403)
        signature = request.headers.get('X-Twilio-Signature')
        if signature:
            url = base_url() + request.path + '?' + request.query_string.decode('ascii')
            if not RequestValidator(required('TWILIO_AUTH_TOKEN')).validate(url, request.form, signature):
                abort(403, description='Signature provided but invalid; check public URL and credentials.')
        with database() as con:
            con.execute('UPDATE demo_calls SET hops=hops+1 WHERE token_hash=?', (digest,))
        g.entry = entry
        g.digest = digest
        g.token = token
        print('Callback:', request.path, '| authentication:', 'signature + call token' if signature else 'call token', flush=True)
        if entry['hops'] >= 8:
            return finish('This short trial call has reached its step limit. Please try a fresh call with crop and kilograms together.')
        return fn(*args, **kwargs)
    return wrapper

def callback(path):
    return base_url() + path + '?' + urlencode({'k': g.token})

def xml(r):
    return Response(str(r), mimetype='text/xml')

def say(r, text, lang='en'):
    if lang == 'te':
        r.say(text, voice='Polly.Aditi', language='te-IN')
    else:
        r.say(text, voice='Polly.Joanna', language='en-US')

def finish(text):
    update(g.digest, stage='done', expires=0)
    r = VoiceResponse()
    say(r, text)
    r.hangup()
    return xml(r)

def ask(text, path='/demo/capture', keypad=False, lang='en'):
    r = VoiceResponse()
    if keypad:
        params = {'num_digits': 1}
        gather = Gather(input='dtmf', action=callback(path), method='POST',
                        timeout=8, action_on_empty_result=True, **params)
    else:
        speech_lang = 'te-IN' if lang == 'te' else 'en-IN'
        params = {'language': speech_lang, 'speech_timeout': 'auto'}
        gather = Gather(input='speech', action=callback(path), method='POST',
                        timeout=8, action_on_empty_result=True, **params)
    say(gather, text, lang)
    r.append(gather)
    r.hangup()
    return xml(r)

def waiting(first=False):
    r = VoiceResponse()
    if first:
        say(r, 'One moment while I understand your harvest details.')
    r.pause(length=5)
    r.redirect(callback('/demo/result'), method='POST')
    return xml(r)

def work(digest, speech, previous):
    try:
        fields = extract(speech, previous)
        if read(digest)['stage'] == 'processing':
            update(digest, fields=json.dumps(fields), stage='ready')
        print('AI extraction finished.', flush=True)
    except Exception as exc:
        message = str(exc) if isinstance(exc, (AIError, ValueError)) else 'AI processing failed.'
        update(digest, error=message, stage='ai_error')
        print('AI:', message, flush=True)

@app.get('/health')
def health():
    return {'service': 'Fasal Mitra Free Demo v2', 'status': 'running'}

@app.post('/demo/voice')
@authenticated
def voice():
    if g.entry['stage'] != 'new':
        return finish('Please start a fresh demo call.')
    update(g.digest, stage='language')
    return ask('Welcome to Fasal Mitra. Press 1 for English. Press 2 for Telugu.',
               '/demo/language', keypad=True)

@app.post('/demo/language')
@authenticated
def language():
    if g.entry['stage'] != 'language':
        return finish('Please start a fresh demo call.')

    digit = request.form.get('Digits', '').strip()

    if digit == '1':
        update(g.digest, stage='listening', language='en')
        return ask(
            'English selected. Please tell me your crop and quantity. '
            'For example, I harvested twenty kilograms of rice.',
            '/demo/capture', lang='en'
        )

    if digit == '2':
        update(g.digest, stage='listening', language='te')
        return ask(
            'తెలుగు ఎంచుకున్నారు. మీరు పండించిన పంట పేరు మరియు ఎంత కిలోలు ఉందో చెప్పండి. '
            'ఉదాహరణకు, నాకు ఇరవై కిలోల వరి పంట వచ్చింది అని చెప్పండి.',
            '/demo/capture', lang='te'
        )

    update(g.digest, stage='language')
    return ask(
        'Invalid choice. Press 1 for English. Press 2 for Telugu.',
        '/demo/language', keypad=True
    )

@app.post('/demo/capture')
@authenticated
def capture():
    if g.entry['stage'] == 'processing':
        return waiting()
    if g.entry['stage'] != 'listening':
        return finish('Please start a fresh demo call.')
    if g.entry['turns'] >= 2:
        return finish('I could not get both details. Please try again and say the crop and weight in kilograms.')
    speech = request.form.get('SpeechResult', '').strip()
    lang = g.entry.get('language') or 'en'
    update(g.digest, turns=g.entry['turns'] + 1)
    if not speech:
        if lang == 'te':
            return ask('నాకు వినిపించలేదు. దయచేసి మీ పంట పేరు మరియు కిలోలలో బరువు చెప్పండి.',
                       '/demo/capture', lang='te')
        return ask('I did not hear that. Please say your crop and weight in kilograms.',
                   '/demo/capture', lang='en')
    # Atomic transition prevents duplicate provider callbacks from starting extra AI requests.
    with database() as con:
        changed = con.execute("UPDATE demo_calls SET stage='processing', started=? WHERE token_hash=? AND stage='listening'",
                              (time.time(), g.digest)).rowcount
    if changed:
        pool.submit(work, g.digest, speech[:1200], json.loads(g.entry['fields']))
    return waiting(first=True)

@app.post('/demo/result')
@authenticated
def result():
    entry = read(g.digest)
    if entry['stage'] == 'processing':
        if time.time() - entry['started'] > 35:
            return finish('The AI service is taking too long. Please check the laptop message and try later.')
        return waiting()
    if entry['stage'] == 'ai_error':
        return finish('The AI service could not process this request. Please check the laptop for the reason. No result was guessed.')
    if entry['stage'] != 'ready':
        return finish('Please start a fresh demo call.')
    fields = json.loads(entry['fields'])
    if fields.get('crop') == 'Other':
        return finish('This demo supports rice, paddy, tomato, onion, maize, wheat and spinach. Please try one of these crops.')
    if not fields.get('crop') or not fields.get('kg'):
        if entry['turns'] >= 2:
            return finish('I could not get both details. Please try a fresh call with crop and kilograms together.')
        lang = entry.get('language') or 'en'
        update(g.digest, stage='listening')
        if lang == 'te':
            prompt = ('మీరు ఏ పంట పండించారు?' if not fields.get('crop')
                      else 'ఎన్ని కిలోలు? దయచేసి కిలోలలో బరువు చెప్పండి.')
        else:
            prompt = ('Which crop did you harvest?' if not fields.get('crop')
                      else 'How many kilograms? Please say the weight in kilograms.')
        return ask(prompt, '/demo/capture', lang=lang)
    # Readback confirmation is spoken, not a crop keypad menu.
    update(g.digest, stage='confirm')
    lang = entry.get('language') or 'en'
    if lang == 'te':
        prompt = (f'మీరు {fields["crop"].lower()} పంటను {fields["kg"]:g} కిలోలు అని చెప్పారు. '
                  'ఇది సరైనదేనా? అవును లేదా కాదు అని చెప్పండి.')
    else:
        prompt = (f'I heard {fields["kg"]:g} kilograms of {fields["crop"].lower()}. '
                  'Is that correct? Please say yes or no.')
    return ask(prompt, '/demo/confirm', lang=lang)

@app.post('/demo/confirm')
@authenticated
def confirm():
    if g.entry['stage'] != 'confirm':
        return finish('Please start a fresh call.')
    raw = request.form.get('SpeechResult', '').strip().lower()
    words = set(re.findall(r'[a-z]+', raw))
    yes = (
        bool(words & {'yes', 'yeah', 'yep', 'correct'})
        and not bool(words & {'no', 'not', 'incorrect'})
    ) or any(x in raw for x in ('అవును', 'అవునండి', 'సరే', 'కరెక్ట్'))
    if not yes:
        return finish('I will not use unconfirmed details. Please start a fresh call and repeat your crop and kilograms.')
    summary = recommend(json.loads(g.entry['fields']))
    update(g.digest, result=summary)
    if config().get('DEMO_SMS_ENABLED') == '1':
        update(g.digest, stage='sms_consent')
        return ask(summary + ' To receive this demo summary by SMS, press 1. Otherwise hang up.', '/demo/sms', keypad=True)
    return finish(summary + ' Thank you for trying Fasal Mitra.')

@app.post('/demo/sms')
@authenticated
def sms():
    if g.entry['stage'] != 'sms_consent' or request.form.get('Digits') != '1':
        return finish('No SMS requested. Thank you.')
    if config().get('DEMO_SMS_ENABLED') != '1':
        return finish('SMS is disabled for this demo.')
    with database() as con:
        changed = con.execute("UPDATE demo_calls SET sms_state='sending' WHERE token_hash=? AND sms_state IS NULL",
                              (g.digest,)).rowcount
    if changed:
        pool.submit(send_sms, g.digest, g.entry['phone'], g.entry['result'])
    return finish('Your SMS request is being processed. Delivery depends on the trial account permissions. Thank you.')

def send_sms(digest, phone, summary):
    try:
        msg = client().messages.create(to=phone, from_=required('TWILIO_SMS_FROM'), body='DEMO ONLY. ' + summary)
        update(digest, sms_state=msg.status, sms_sid=msg.sid)
        print('SMS submitted; delivery not yet confirmed. Run demo_status.py later.', flush=True)
    except Exception as exc:
        update(digest, sms_state='failed_or_unknown')
        print('SMS failed or outcome unknown. Error code:', getattr(exc, 'code', type(exc).__name__), flush=True)

if __name__ == '__main__':
    try:
        base_url()
        required('TWILIO_AUTH_TOKEN')
        required('TWILIO_ACCOUNT_SID')
        allowed_numbers()
        init_db()
        print('Fasal Mitra Free Demo v2 - keep this terminal running.', flush=True)
        print('Health: http://127.0.0.1:5000/health | No calls sent at startup.', flush=True)
        app.run(host='127.0.0.1', port=5000, debug=False, threaded=True)
    except ValueError as exc:
        print(str(exc))
