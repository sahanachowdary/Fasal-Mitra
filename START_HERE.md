# Fasal Mitra: short voice demo (v2)

This is a separate demo edition. Copy ALL these files into your EXISTING
Fasal-Mitra-AI-Calls folder containing `.venv` and `.env`. Do not run the old
voice_server.py alongside this server. Original files remain usable and unchanged.

## What this demonstrates

A real outbound phone call to a consenting, Twilio-verified team member.
They speak English, e.g. **I harvested twenty kilograms of rice**.
Twilio transcribes the speech. Gemini extracts the crop and kilograms.
The call reads the details back; the user says **yes**. A deterministic comparison
of invented buyer listings provides a spoken recommendation.
The farmer uses an ordinary phone; your laptop needs internet and must stay awake.
This version is tested for English prompts; Telugu speech is not validated.

No OpenAI key or OpenAI credits are used. Gemini and Twilio free/trial quotas still
apply. Nothing here upgrades an account or guarantees that quotas are available.
The software is ready for live verification, NOT certified as tested with your account.

## 1. Stop yesterday's server

In its terminal press Ctrl+C. Stop old ngrok with Ctrl+C too so that only one tunnel
will run. Keep VS Code open on your original project folder.

## 2. Setup (no network call, no SMS)

Run in the VS Code terminal:

```powershell
.\.venv\Scripts\python.exe demo_setup.py
```

This reuses the Twilio settings in your old `.env` and writes a separate `.demo.env`.
For the ngrok domain, press Enter to keep your saved domain if it is correct.
When asked for a Gemini key, you may press Enter to skip it for the first test.
Typing/pasting a hidden key will not show characters: this is normal.
Do not paste tokens or configuration screenshots into chat.

If a dependency is missing, install using:

```powershell
.\.venv\Scripts\python.exe -m pip install -r demo_requirements.txt
```

## 3. Start server and tunnel (two terminals)

Terminal A:

```powershell
.\.venv\Scripts\python.exe demo_server.py
```

Leave it running. Do NOT press Ctrl+C to type the next command.
Use Terminal > New Terminal for Terminal B:

```powershell
ngrok http 5000
```

Check that the forwarding HTTPS domain is the same as PUBLIC_BASE_URL. A changed
domain means rerun setup and restart the demo server. Never paste the full arrow line.
Opening PUBLIC_BASE_URL/health should show service **Fasal Mitra Free Demo v2**.
The old server's `running` response is not sufficient.

## 4. Welcome call first (third terminal)

This command makes ONE real call to the first number in ALLOWED_TEST_NUMBERS.
Run it only when that person has agreed and is ready to answer.

```powershell
.\.venv\Scripts\python.exe demo_call.py --welcome-only --consent-confirmed
```

Expected: a welcome message saying the call is connected to your laptop.
No Gemini request is made. The command sets up its own authenticated URL;
do NOT enter /demo/voice manually in the Twilio Console.

If it fails, stop repeating calls and capture the server's short output.
Do NOT share ngrok URLs/query strings containing `k=`, which are credentials.
The call command sends only to/from/url because extra parameters were rejected
by this user's trial. Account restrictions may still prevent a live test.

## 5. Free Gemini setup and one text test

Create a key at https://aistudio.google.com/apikey using a free-tier project.
Do not enable paid billing for this zero-spend demo. Free-tier availability and
limits are account/model dependent. Use fictional harvest details; free-tier inputs
may be used by Google for product improvement.

Run demo_setup.py again and paste the key privately. Then:

```powershell
.\.venv\Scripts\python.exe demo_ai_test.py
```

Press Enter to test rice, 20 kg. Expected crop Rice, kg 20, Demo Local Buyer,
fictional Rs 30/kg, Rs 600 after assumed zero transport. The large buyer offers
Rs 32/kg but Rs 100 transport, so its Rs 540 net is lower.
For 200 kg rice, the wholesale sample is better (Rs 6,300 vs Rs 6,000).
These numbers are invented illustrations, NOT real market data or quotations.

## 6. Actual AI phone conversation

Keep Terminal A and B running. In Terminal C:

```powershell
.\.venv\Scripts\python.exe demo_call.py --consent-confirmed
```

Answer, wait for the question, speak one sentence clearly. Say **yes** when asked
to confirm. Crop choices are spoken, never a numbered menu. Allowed crops:
rice, paddy (distinct from rice), tomato, onion, maize, wheat, spinach.
The model can convert explicit quintals or tonnes into kg. Unknown bag weights
require clarification. Unsupported crops get an honest limitation message.

Use short answers for the trial. AI work runs in the background so webhooks return
quickly; the call waits and polls briefly. There is a maximum of nine callbacks,
two harvest-input attempts and a five-minute local credential lifetime. If AI is
slow or quota is unavailable, the call says it could not process the request.
It never substitutes a fake AI success or repeats a fixed answer as if generated.

## Optional SMS (after calls work)

SMS is OFF by default to keep the first demo focused. To enable, set
DEMO_SMS_ENABLED='1' in .demo.env and configure TWILIO_SMS_FROM. Then, after the
spoken recommendation, press 1 to explicitly request ONE summary SMS.
This keypad option is only for SMS consent, never crop selection.
Custom SMS may be restricted even if Twilio sample messages worked. The app
does not claim delivery just because Twilio accepts the request. Run:

```powershell
.\.venv\Scripts\python.exe demo_status.py
```

## Authentication and scope

The original signature-checked server is NOT modified. This separate outbound-only
demo uses a randomly generated 256-bit bearer credential for each call, hashed in
SQLite, expiring in five minutes, and tied to the SID returned by YOUR authenticated
Twilio Calls API request. Every callback needs that credential, matching account/SID,
and an allowed recipient. A Twilio signature, if present, must also validate.
This is alternative application authentication, not verification of missing Twilio
signatures. It neither enables provider features nor bypasses Twilio's trial limits.
There is no public route that starts a call or arbitrary AI work. One active session
at a time and 20 attempts/day are allowed. SMS has an atomic once-per-call reservation.

Credential URLs appear in ngrok/Twilio request inspectors: keep those private.
Console access logs suppress query strings; application logs do not print keys,
speech or full URLs. Local SQLite retains phone/CallSid/extracted fields briefly;
old sessions are removed at setup/start after 24 hours. Twilio/Google have separate
retention policies. This is a supervised hackathon demo, not a production service.
If a call is abandoned, its local session expires after five minutes. Calls remain
subject to Twilio's own trial call duration limit; credential expiry does not itself
terminate an already playing call. Hang up when finished.

## Presentation wording

After successful live testing: "Our demo accepts spoken crop and quantity over a
normal phone call. Gemini extracts the details, and our matching logic recommends
from sample buyer listings. Live prices, verified buyers, regional-language testing,
inbound/missed-call access and production deployment are future work."

No agricultural safety or perishability prediction is made. No real buyer booking
occurs. Low recognition accuracy should be described honestly, not hidden.

## Troubleshooting

- Wrong /health service: stop voice_server.py and start demo_server.py.
- 403 missing credential: use demo_call.py, not the old script or Console URL.
- 403 expired/not registered: use a fresh call; old URLs cannot be reused.
- 403 signature provided but invalid: verify public domain and Twilio credentials.
- Gemini 429: free quota unavailable/exhausted; waiting or another eligible free
  project/model may be needed. Do not create accounts to evade limits.
- Gemini 400/403: check key, model, region and project access in AI Studio.
- No ringing: use returned Twilio error code; ensure verified To and correct From.
- Cannot connect: verify tunnel domain and server, use three separate terminals.
- SMS failed/unknown: inspect provider logs before retrying; never auto-resend.

## Reference documentation

- https://www.twilio.com/docs/usage/trials/try-out-voice
- https://www.twilio.com/docs/voice/twiml/gather
- https://ai.google.dev/api/generate-content
- https://ai.google.dev/gemini-api/docs/pricing

Run mock tests with `.\.venv\Scripts\python.exe -m unittest test_demo -v`.
They do not contact providers, use credits, make calls or send SMS.
