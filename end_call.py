from twilio.rest import Client
from demo_common import required, client

twilio = client()

calls = twilio.calls.list(limit=20)

for call in calls:
    if call.status in ["queued", "ringing", "in-progress"]:
        print("Ending:", call.sid, call.status, call.to)
        twilio.calls(call.sid).update(status="completed")
        print("CALL ENDED")