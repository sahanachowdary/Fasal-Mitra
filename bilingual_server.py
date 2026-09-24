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
from bilingual_common import (AIError, allowed_numbers, base_url, client, config, database,
                         extract, init_db, recommend, required, token_hash)

INTRO = 'Welcome to Fasal Mitra, an AI harvest demo. Buyer names and prices are fictional. By continuing, you agree to speech processing by Twilio and Google. Please tell me your crop and quantity. For example, I harvested twenty kilograms of rice.'
TELUGU = {'This short trial call has reached its step limit. Please try a fresh call with crop and kilograms together.': 'ఈ చిన్న డెమో కాల్ పరిమితి పూర్తయింది. మళ్ళీ కాల్ చేసి పంట పేరు, కిలోలు కలిపి చెప్పండి.', 'Please start a fresh demo call.': 'దయచేసి కొత్త డెమో కాల్ ప్రారంభించండి.', 'Please start a fresh call.': 'దయచేసి మళ్ళీ కాల్ చేయండి.', 'One moment while I understand your harvest details.': 'మీ పంట వివరాలు అర్థం చేసుకుంటున్నాను. కొద్దిసేపు వేచి ఉండండి.', 'I could not get both details. Please try again and say the crop and weight in kilograms.': 'రెండు వివరాలు అందలేదు. మళ్ళీ కాల్ చేసి పంట పేరు, బరువు కిలోల్లో చెప్పండి.', 'I did not hear that. Please say your crop and weight in kilograms.': 'మీ మాట వినిపించలేదు. పంట పేరు, బరువు కిలోల్లో చెప్పండి.', 'The AI service is taking too long. Please check the laptop message and try later.': 'ఏ ఐ సేవకు ఎక్కువ సమయం పడుతోంది. ల్యాప్ టాప్ లో సందేశం చూసి తరువాత ప్రయత్నించండి.', 'The AI service could not process this request. Please check the laptop for the reason. No result was guessed.': 'ఏ ఐ సేవ ఈ వివరాలు అర్థం చేసుకోలేకపోయింది. కారణం కోసం ల్యాప్ టాప్ చూడండి. ఊహించి ఫలితం ఇవ్వలేదు.', 'This demo supports rice, paddy, tomato, onion, maize, wheat and spinach. Please try one of these crops.': 'ఈ డెమోలో బియ్యం, వడ్లు, టమాటాలు, ఉల్లిపాయలు, మొక్కజొన్న, గోధుమలు, పాలకూర ఉన్నాయి. వీటిలో ఒక పంటతో ప్రయత్నించండి.', 'I could not get both details. Please try a fresh call with crop and kilograms together.': 'రెండు వివరాలు అందలేదు. మళ్ళీ కాల్ చేసి పంట పేరు, కిలోలు కలిపి చెప్పండి.', 'Which crop did you harvest?': 'మీ పంట పేరు చెప్పండి.', 'How many kilograms? Please say the weight in kilograms.': 'ఎన్ని కిలోలు? దయచేసి బరువు కిలోల్లో చెప్పండి.', 'I will not use unconfirmed details. Please start a fresh call and repeat your crop and kilograms.': 'వివరాలు నిర్ధారణ కాలేదు కాబట్టి సూచన ఇవ్వడం లేదు. మళ్ళీ కాల్ చేసి పంట పేరు, కిలోలు చెప్పండి.', 'No SMS requested. Thank you.': 'ఎస్ ఎం ఎస్ కోరలేదు. ధన్యవాదాలు.', 'SMS is disabled for this demo.': 'ఈ డెమోలో ఎస్ ఎం ఎస్ సౌకర్యం ఆఫ్ లో ఉంది.', 'Your SMS request is being processed. Delivery depends on the trial account permissions. Thank you.': 'మీ ఎస్ ఎం ఎస్ అభ్యర్థన పంపుతున్నాము. సందేశం చేరడం ట్రయల్ ఖాతా అనుమతులపై ఆధారపడి ఉంటుంది. ధన్యవాదాలు.', 'Welcome to Fasal Mitra, an AI harvest demo. Buyer names and prices are fictional. By continuing, you agree to speech processing by Twilio and Google. Please tell me your crop and quantity. For example, I harvested twenty kilograms of rice.': 'ఫసల్ మిత్రకు స్వాగతం. ఇది ఏ ఐ పంట డెమో. కొనుగోలుదారులు, ధరలు నమూనా మాత్రమే. కొనసాగితే మీ మాటలను ట్విలియో, గూగుల్ ప్రాసెస్ చేయడానికి అంగీకరిస్తున్నారు. మీ పంట పేరు, ఎన్ని కిలోలో చెప్పండి. ఉదాహరణకు, నా దగ్గర యాభై కిలోల ఉల్లిపాయలు ఉన్నాయి.'}

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
            abort(403, description='Missing demo call credential. Start calls with bilingual_call.py.')
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

def language():
    return g.entry.get('language', 'en')

def say(r, text):
    if language() == 'te':
        text = TELUGU.get(text, text)
        match = re.fullmatch(r'I heard ([0-9.]+) kilograms of ([a-z]+)\. Is that correct\? Please say yes or no\.', text)
        if match:
            crop = {'rice':'బియ్యం','paddy':'వడ్లు','tomato':'టమాటాలు','onion':'ఉల్లిపాయలు','maize':'మొక్కజొన్న','wheat':'గోధుమలు','spinach':'పాలకూర'}.get(match[2], match[2])
            text = f'మీరు {match[1]} కిలోల {crop} అని చెప్పారు. సరైనదేనా? అవును లేదా కాదు అని చెప్పండి.'
        r.say(text, voice='Google.te-IN-Standard-A', language='te-IN')
    else:
        r.say(text, voice='Polly.Joanna', language='en-US')

def finish(text):
    update(g.digest, stage='done', expires=0)
    r = VoiceResponse()
    say(r, text)
    r.hangup()
    return xml(r)

def ask(text, path='/demo/capture', keypad=False):
    r = VoiceResponse()
    params = {'num_digits': 1} if keypad else ({'language': 'te-IN', 'speech_timeout': 2} if language() == 'te' else {'language': 'en-IN', 'speech_timeout': 'auto'})
    gather = Gather(input='dtmf' if keypad else 'speech', action=callback(path), method='POST',
                    timeout=8, action_on_empty_result=True, **params)
    say(gather, text)
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
    return {'service': 'Fasal Mitra Bilingual v1', 'status': 'running'}

@app.post('/demo/voice')
@authenticated
def voice():
    if g.entry['mode'] == 'welcome':
        return finish('Welcome to Fasal Mitra. Your real phone call is connected to your laptop. '
                      'This was the connection test. Thank you.')
    if g.entry['stage'] != 'new':
        return finish('Please start a fresh demo call.')
    update(g.digest, stage='language')
    return language_menu()

def language_menu():
    r = VoiceResponse()
    gather = Gather(input='dtmf', num_digits=1, action=callback('/demo/language'),
                    method='POST', timeout=8, action_on_empty_result=True)
    gather.say('Welcome to Fasal Mitra. Press 1 for English.', voice='Polly.Joanna', language='en-US')
    gather.say('తెలుగు కోసం రెండు నొక్కండి.', voice='Google.te-IN-Standard-A', language='te-IN')
    r.append(gather)
    r.hangup()
    return xml(r)

@app.post('/demo/language')
@authenticated
def choose_language():
    if g.entry['stage'] != 'language':
        return finish('Please start a fresh demo call.')
    digit = request.form.get('Digits', '')
    if digit not in ('1', '2'):
        if g.entry['menu_tries'] >= 1:
            r = VoiceResponse()
            r.say('No language selected. Please try a new call.', voice='Polly.Joanna', language='en-US')
            r.say('భాష ఎంపిక కాలేదు. దయచేసి మళ్ళీ కాల్ చేయండి.', voice='Google.te-IN-Standard-A', language='te-IN')
            r.hangup()
            update(g.digest, stage='done', expires=0)
            return xml(r)
        update(g.digest, menu_tries=g.entry['menu_tries']+1)
        return language_menu()
    chosen = 'en' if digit == '1' else 'te'
    update(g.digest, stage='listening', language=chosen)
    g.entry['language'] = chosen
    return ask(INTRO)

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
    update(g.digest, turns=g.entry['turns'] + 1)
    if not speech:
        return ask('I did not hear that. Please say your crop and weight in kilograms.')
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
        update(g.digest, stage='listening')
        return ask('Which crop did you harvest?' if not fields.get('crop') else 'How many kilograms? Please say the weight in kilograms.')
    # Readback confirmation is spoken, not a crop keypad menu.
    update(g.digest, stage='confirm')
    return ask(f'I heard {fields["kg"]:g} kilograms of {fields["crop"].lower()}. Is that correct? Please say yes or no.', '/demo/confirm')

@app.post('/demo/confirm')
@authenticated
def confirm():
    if g.entry['stage'] != 'confirm':
        return finish('Please start a fresh call.')
    speech = request.form.get('SpeechResult', '').lower()
    words = set(re.findall(r'[a-z]+|[\u0c00-\u0c7f]+', speech))
    yes = bool(words & {'yes', 'yeah', 'yep', 'correct', 'అవును', 'ఔను', 'సరే', 'సరైనదే', 'avunu', 'aunu'}) and not bool(words & {'no', 'not', 'incorrect', 'కాదు', 'లేదు', 'వద్దు', 'కాదండి', 'లేదండి', 'kaadu', 'ledu'})
    if not yes:
        return finish('I will not use unconfirmed details. Please start a fresh call and repeat your crop and kilograms.')
    summary = recommend(json.loads(g.entry['fields']), language())
    update(g.digest, result=summary)
    if config().get('DEMO_SMS_ENABLED') == '1':
        update(g.digest, stage='sms_consent')
        return ask(summary + (' ఈ నమూనా వివరాలు ఎస్ ఎం ఎస్ ద్వారా కావాలంటే ఒకటి నొక్కండి. లేకపోతే కాల్ ముగించండి.' if language() == 'te' else ' To receive this demo summary by SMS, press 1. Otherwise hang up.'), '/demo/sms', keypad=True)
    return finish(summary + (' ఫసల్ మిత్రను ఉపయోగించినందుకు ధన్యవాదాలు.' if language() == 'te' else ' Thank you for trying Fasal Mitra.'))

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
        print('SMS submitted; delivery not yet confirmed. Run bilingual_status.py later.', flush=True)
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
        print('Fasal Mitra Bilingual v1 - keep this terminal running.', flush=True)
        print('Health: http://127.0.0.1:5000/health | No calls sent at startup.', flush=True)
        app.run(host='127.0.0.1', port=5000, debug=False, threaded=True)
    except ValueError as exc:
        print(str(exc))
