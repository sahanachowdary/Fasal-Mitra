# Fasal Mitra: AI phone calls + SMS

This is a Python integration you can run on your Windows laptop. It uses real OpenAI and Twilio SDK calls, with a controlled test-phone allowlist. It is NOT already activated: you must supply working accounts, credentials, permitted senders and a public HTTPS webhook URL. No live call, SMS or AI request was made during development.

## What the farmer experiences
1. Your test phone receives a call initiated by the team, or calls an enabled Twilio number.
2. The voice explains that this is an AI demo and asks the farmer to press 1 to continue.
3. The farmer speaks: "I have two hundred kilograms of tomatoes."
4. Twilio transcribes the speech; OpenAI extracts the fields. The app asks for missing weight, temperature, harvest age, radius or local offer. No guessed bag weights.
5. It reads back all fields. The farmer confirms with 1 or restarts details with 2.
6. The app speaks the best sample buyer and net income after transport.
7. The farmer presses 1 for one SMS summary, or 2 to finish without a message.

This is a turn-by-turn English AI phone assistant, with keypad confirmation. It is not an interruptible realtime speech agent. The AI extracts natural-language information; Python performs matching and arithmetic. Prompts and results are spoken using Twilio text-to-speech. Phone calls, speech processing, SMS and AI usage may incur separate charges.

## Before paying: check India support
Twilio currently describes outbound calls to India as originating from a non-Indian number. Its Voice trial also requires verified recipients and restricts calling geography. Confirm your specific account can call your +91 test phone and use speech Gather before buying a number or relying on a trial. An inbound call to a foreign number can involve international calling charges. A local Indian missed-call helpline is NOT supplied by this package.

SMS to India depends on your account, sender and routing. Twilio distinguishes international routing from domestic DLT-registered sender routing. Confirm the applicable route with Twilio. Do not assume a voice-enabled number can also send SMS. In this version SMS is an outbound summary only, not a two-way SMS chatbot.

Sources: [India voice](https://www.twilio.com/en-us/guidelines/in/voice), [Voice trial](https://www.twilio.com/docs/usage/trials/try-out-voice), [India SMS](https://www.twilio.com/en-us/guidelines/in/sms).

## Accounts you need
- OpenAI API project, API key and available API billing/credits, with access to the configured model.
- Twilio account, Account SID, Auth Token, a permitted voice sender and an SMS sender, and permission to contact the test country/number.
- A public HTTPS tunnel such as ngrok, installed and authenticated on your laptop.
- A consenting team member's mobile number, in full +countrycode format.

Enter secrets only into your local .env file. Do not put them in screenshots, GitHub or chat.

## Windows setup
Extract this ZIP and open the extracted folder in VS Code. In its terminal:

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

The commands avoid needing PowerShell activation. Use Python 3.10 or newer. Open `.env` in VS Code and replace every placeholder. `TWILIO_VOICE_FROM` is the Twilio voice sender; `TWILIO_SMS_FROM` is the separately permitted SMS sender. Put only consenting team phones in `ALLOWED_TEST_NUMBERS`, separated by commas. Set `OPENAI_MODEL` to an accessible structured-output model; the default is `gpt-4.1-mini`.

Open a second terminal and start your authenticated tunnel:

```powershell
ngrok http 5000
```

Copy its HTTPS forwarding origin into `PUBLIC_BASE_URL`, such as `https://your-host.ngrok-free.app`. Use only the origin, no path or query. See [ngrok setup](https://ngrok.com/docs/start).

Then run in the project terminal:

```powershell
.venv\Scripts\python.exe voice_server.py
```

Leave the server and tunnel running. Visit your HTTPS URL followed by `/health`; it should display a small JSON status response. This proves reachability, not provider account eligibility. Restart the server after changing .env. Update PUBLIC_BASE_URL whenever the tunnel address changes. Never disable webhook signature checks to fix a URL mismatch.

## Make the first real test call
Once the recipient has agreed, use a third terminal in the project folder. Replace the sample number below with your allowlisted test phone:

```powershell
.venv\Scripts\python.exe call_farmer.py +91YOURNUMBER --consent-confirmed
```

This command makes one actual outbound call and can incur charges. Merely starting the server does not call anyone. The outbound test is capped at five minutes. Check the Twilio call logs if your phone does not ring.

For inbound calls, configure the voice-capable number's incoming-call webhook in Twilio to `https://YOUR_HOST/voice` with HTTP POST. The caller must be in ALLOWED_TEST_NUMBERS. Outbound calls use the webhook configured by call_farmer.py and do not require this inbound setting.

## Demo script
- Press 1 after the introduction.
- Say "I have two hundred kilograms of tomatoes."
- Answer follow-ups: "32 degrees", "one hour", "15 kilometres", "6 rupees per kilogram".
- Press 1 after the readback.
- Hear the sample result: Rs 3,650 net for the fictional City wholesale buyer.
- Press 1 for the SMS. Show the actual received message to the judges.

The weather is provided by the caller, not fetched live. The listings and time-window rule remain fictional demonstration inputs. Say this plainly. This proves the voice-to-AI-to-matching-to-SMS workflow, not agricultural prediction accuracy or verified market availability.

## See SMS status

```powershell
.venv\Scripts\python.exe check_status.py
```

`queued` means submitted, not delivered. `delivered` means a provider delivery callback was received. `failed_or_unknown` means submission failed or timed out; check Twilio logs before attempting another call. There is deliberately no automatic retry that could send duplicate messages. Delivery callbacks update local state when Twilio supplies them. Logs are a demo aid, not a production monitoring system.

## Files and concepts to explain to judges
| File | Purpose |
|---|---|
| voice_server.py | Phone conversation, AI extraction, signed webhooks, SMS submission |
| matching.py | Explainable crop/capacity/radius matching and arithmetic |
| call_farmer.py | Initiates one agreed test call |
| check_status.py | Reads local SMS submission/delivery status |
| test_voice.py | Eleven tests using mocked provider responses |
| .env.example | Template for your private configuration |
| calls.db | Created at runtime; stores phone/session fields and SMS state |

The server stores structured fields, not raw speech recordings or transcripts. Speech text is sent to OpenAI with store=False; this does not override providers' own retention policies. Phone metadata is handled by Twilio and your tunnel service. The local database contains test phone numbers; keep it private and remove it after the demo if no longer needed. The code has no payments, buyer reservations or real sale confirmation.

## Tests and known limitations

```powershell
.venv\Scripts\python.exe -m unittest -v
```

Eleven tests passed during development, covering the signed call flow, consent, missing fields, AI failure, duplicate SMS prevention, allowlisting and delivery callbacks. These tests use mocked AI/telecom responses. SDK imports were verified with the versions in requirements.txt. Live AI extraction quality, carrier audio, SMS delivery and end-to-end latency still require your account-backed test.

The Flask development server plus tunnel is for a supervised hackathon demonstration. Keep the allowlist. A deployed public service needs production hosting, robust job/state handling, account-level spending limits, monitoring and provider onboarding. Sessions expire logically after 30 minutes but records remain until removed. AI calls time out after 8 seconds and ask the user to retry; test this on the event network. Prompts are English only. Telugu/Hindi speech support, missed-call callbacks and real buyer registration are future work, not features of this package.

## Official implementation references
- [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs): constrains extraction to defined fields; the app still checks ranges and requests readback confirmation.
- [GPT-4.1 mini](https://developers.openai.com/api/docs/models/gpt-4.1-mini): configured model reference; account access must be checked.
- [Twilio Gather](https://www.twilio.com/docs/voice/twiml/gather): speech and keypad input.
- [Twilio webhook security](https://www.twilio.com/docs/usage/security): request signatures verified using the SDK and exact public URL.
- [Twilio Calls API](https://www.twilio.com/docs/voice/api/call-resource): outbound phone call creation.
- [Twilio Messages API](https://www.twilio.com/docs/messaging/api/message-resource): SMS submission and delivery status.
