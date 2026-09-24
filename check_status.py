"""Read local submission and delivery status without exposing phone numbers."""
from voice_server import db
if __name__ == '__main__':
    with db() as con:
        rows = con.execute('SELECT call_sid,message_sid,state FROM sms').fetchall()
    for sid, message, state in rows:
        print(sid[-8:], message[-8:] or '(no message SID)', state)
    if not rows:
        print('No SMS requests yet.')
