"""Read-only status lookup. Never sends another SMS or call."""
from bilingual_common import client, database, init_db

if __name__ == '__main__':
    init_db()
    with database() as con:
        row = con.execute('SELECT * FROM demo_calls ORDER BY created DESC LIMIT 1').fetchone()
    if not row:
        print('No demo call yet.')
    else:
        print('Local stage:', row['stage'])
        if row['error']:
            print('AI:', row['error'])
        if row['sms_sid']:
            try:
                msg = client().messages(row['sms_sid']).fetch()
                print('SMS provider status:', msg.status, '| error code:', msg.error_code)
            except Exception as exc:
                print('Could not fetch SMS status:', type(exc).__name__)
        else:
            print('SMS:', row['sms_state'] or 'not requested')
