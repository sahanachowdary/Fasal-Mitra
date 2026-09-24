"""Initiate one call to a consenting, allowlisted test phone."""
import argparse
from voice_server import (
    check_config, allowed_numbers, twilio_client, public_url, required
)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phone', help='Phone number with country code')
    parser.add_argument('--consent-confirmed', action='store_true')
    args = parser.parse_args()

    check_config()

    if args.phone not in allowed_numbers():
        parser.error('Recipient must be in ALLOWED_TEST_NUMBERS.')

    if not args.consent_confirmed:
        parser.error('Get consent, then add --consent-confirmed.')

    print('Requesting call...', flush=True)
    call = twilio_client().calls.create(
        to=args.phone,
        from_=required('TWILIO_VOICE_FROM'),
        url=public_url('/voice')
    )
    print('Call requested. SID:', call.sid)