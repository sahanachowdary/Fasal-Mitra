"""Make ONE allowlisted test call. No calls occur at import or server startup."""
import argparse
import re
import secrets
import time
import requests
from twilio.base.exceptions import TwilioRestException
from bilingual_common import (base_url, client, required, config, allowed_numbers,
                         database, init_db, token_hash)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--phone', help='Optional; defaults to first allowed test number')
    p.add_argument('--welcome-only', action='store_true', help='Test call audio without Gemini')
    p.add_argument('--consent-confirmed', action='store_true')
    args = p.parse_args()
    if not args.consent_confirmed:
        p.error('Obtain test recipient consent, then add --consent-confirmed.')
    init_db()
    phone = args.phone or required('ALLOWED_TEST_NUMBERS').split(',')[0].strip()
    if phone not in allowed_numbers() or not re.fullmatch(r'\+[1-9]\d{7,14}', phone):
        p.error('Phone must be a valid E.164 number in ALLOWED_TEST_NUMBERS.')
    url = base_url()
    if not args.welcome_only:
        required('GEMINI_API_KEY')
    try:
        health = requests.get(url + '/health', headers={'ngrok-skip-browser-warning': '1'}, timeout=8)
        healthy = health.ok and health.json().get('service') == 'Fasal Mitra Bilingual v1'
    except (requests.RequestException, ValueError):
        healthy = False
    if not healthy:
        print('Demo server not reachable. Start bilingual_server.py and ngrok http 5000 in separate terminals.')
        return
    token = secrets.token_urlsafe(32)
    digest = token_hash(token)
    now = time.time()
    with database() as con:
        con.execute('BEGIN IMMEDIATE')
        count = con.execute('SELECT count(*) FROM demo_calls WHERE created > ?', (now - 86400,)).fetchone()[0]
        active = con.execute("SELECT count(*) FROM demo_calls WHERE expires > ? AND stage NOT IN ('done','failed')", (now,)).fetchone()[0]
        if count >= 20:
            print('Demo daily safety limit reached (20 attempts). No call sent.')
            return
        if active:
            print('Another demo call session is active. Finish it or wait for its five-minute expiry.')
            return
        con.execute('INSERT INTO demo_calls(token_hash,phone,created,expires,mode) VALUES(?,?,?,?,?)',
                    (digest, phone, now, now + 300, 'welcome' if args.welcome_only else 'ai'))
    print('Requesting one test call...', flush=True)
    try:
        call = client().calls.create(to=phone, from_=required('TWILIO_VOICE_FROM'),
                                     url=f'{url}/demo/voice?k={token}')
        with database() as con:
            con.execute('UPDATE demo_calls SET sid=? WHERE token_hash=?', (call.sid, digest))
        print('Call requested. SID:', call.sid)
        print('Keep bilingual_server.py and ngrok running. Answer the call.')
    except TwilioRestException as exc:
        with database() as con:
            con.execute("UPDATE demo_calls SET stage='failed',expires=0 WHERE token_hash=?", (digest,))
        print(f'Twilio rejected the request: HTTP {exc.status}, code {exc.code}.')
        print('Use this code to inspect Twilio logs. No automatic retries; do not share webhook URLs with tokens.')
    except Exception as exc:
        print(f'Call outcome unknown ({type(exc).__name__}). Check Twilio logs before trying again.')

if __name__ == '__main__':
    try:
        main()
    except ValueError as exc:
        print(str(exc))
