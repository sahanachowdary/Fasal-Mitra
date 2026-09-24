"""Interactive local setup. Never send credentials to chat or commit configuration."""
import getpass
import json
import re
from demo_common import ROOT, config, base_url

def main():
    current = config()
    values = {}
    print('Fasal Mitra Free Demo setup. Existing .env is not overwritten.')
    print('Use only a consenting team test number. All buyer data is fictional.\n')
    for name, label, secret in [
        ('TWILIO_ACCOUNT_SID', 'Twilio Account SID', False),
        ('TWILIO_AUTH_TOKEN', 'Twilio Auth Token', True),
        ('TWILIO_VOICE_FROM', 'Twilio trial VOICE number, including +country code', False),
        ('ALLOWED_TEST_NUMBERS', 'Your verified mobile number, including +91', False),
    ]:
        value = current.get(name, '')
        if not value or value.startswith('REPLACE'):
            value = (getpass.getpass(label + ' (hidden): ') if secret else input(label + ': ')).strip()
        if not value:
            raise ValueError(f'{name} is required.')
        values[name] = value
        print(name + ': set (value not displayed)')
    if not re.fullmatch(r'AC[0-9a-fA-F]{32}', values['TWILIO_ACCOUNT_SID']):
        raise ValueError('Account SID format is wrong; copy the Account SID from Twilio.')
    for number in [values['TWILIO_VOICE_FROM'], *values['ALLOWED_TEST_NUMBERS'].split(',')]:
        if not re.fullmatch(r'\+[1-9]\d{7,14}', number.strip()):
            raise ValueError('Numbers must include +country code with digits only.')
    old_url = current.get('PUBLIC_BASE_URL', '')
    entered = input('Public ngrok https domain only [Enter keeps existing]: ').strip()
    values['PUBLIC_BASE_URL'] = entered or old_url
    old_key = current.get('GEMINI_API_KEY', '')
    print('\nGemini key: create in https://aistudio.google.com/apikey on a free-tier project.')
    print('You can press Enter to skip Gemini now and test only the welcome call.')
    key = getpass.getpass('Gemini API key (hidden; Enter keeps existing or skips): ').strip()
    if key or old_key:
        values['GEMINI_API_KEY'] = key or old_key
    values['GEMINI_MODEL'] = current.get('GEMINI_MODEL') or 'gemini-2.5-flash-lite'
    values['DEMO_SMS_ENABLED'] = current.get('DEMO_SMS_ENABLED', '0')
    if current.get('TWILIO_SMS_FROM'):
        values['TWILIO_SMS_FROM'] = current['TWILIO_SMS_FROM']
    from urllib.parse import urlsplit
    parsed = urlsplit(values['PUBLIC_BASE_URL'].rstrip('/'))
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.path or parsed.query
            or parsed.fragment or parsed.username or any(c.isspace() for c in values['PUBLIC_BASE_URL'])):
        raise ValueError('Use only https://your-domain.ngrok-free.dev without arrows or /voice.')
    if any('\n' in value or '\r' in value or "'" in value for value in values.values()):
        raise ValueError('Configuration contains unexpected characters; paste values only.')
    (ROOT / '.demo.env').write_text(''.join(f"{k}='{v}'\n" for k, v in values.items()), encoding='utf-8')
    # Protect secrets if this folder is later committed to Git.
    ignore = ROOT / '.gitignore'
    existing = ignore.read_text(encoding='utf-8') if ignore.exists() else ''
    additions = ['.env', '.demo.env', 'demo_calls.db', '.venv/', '__pycache__/']
    ignore.write_text(existing + '\n' + '\n'.join(x for x in additions if x not in existing.splitlines()) + '\n', encoding='utf-8')
    print('\nSaved. Start demo_server.py and ngrok in separate terminals.')
    print('Do not share .env, .demo.env or ngrok request URLs. They contain credentials.')

if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyboardInterrupt, EOFError) as exc:
        print('Setup stopped:', str(exc))
