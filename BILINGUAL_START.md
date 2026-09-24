# Fasal Mitra: English + Telugu phone demo

This is an add-on to your working project. No new packages or keys are needed.
The English demo files are not overwritten. Existing saved settings are reused.

## Install and run on Windows

1. Extract this ZIP. Copy all files into the SAME folder containing demo_server.py and your saved settings. Do not run from inside the ZIP or a separate nested folder.
2. In the terminal running demo_server.py, press Ctrl+C once. Leave ngrok running.
3. In that server terminal run:

```powershell
.\.venv\Scripts\python.exe bilingual_server.py
```

4. In the separate call terminal run ONCE for your consenting, verified test phone:

```powershell
.\.venv\Scripts\python.exe bilingual_call.py --consent-confirmed
```

5. Answer the call. Press 1 for English or 2 for Telugu on the PHONE keypad.
   Wait until the question ends, then speak the crop and kilograms together.
   English: "I harvested fifty kilograms of onions."
   Telugu: "నా దగ్గర యాభై కిలోల ఉల్లిపాయలు ఉన్నాయి."
   Listen to the readback. If correct, say "Yes" / "అవును".
   If incorrect, say "No" / "కాదు". The demo ends instead of using unconfirmed data.

The crop and quantity are spoken, not selected by keypad. Telugu is spoken in Telugu script through Twilio TTS; Gemini extracts crop and weight from the transcribed speech. Matching is deterministic using fictional sample buyers and prices, not live market data or a booking.

## Test order for the presentation

First make a full call selecting 1. Then make a separate call selecting 2.
Test crop recognition, weight, confirmation and the full response in both.
22 offline tests passed with mocked provider requests. Real Telugu phone recognition and playback MUST be tested on your account; no live calls were made while creating this add-on.

The free-tier Gemini model default is gemini-3.5-flash-lite. Your saved GEMINI_MODEL overrides this, so keep the working model setting. Uses the existing generateContent endpoint; no API migration is needed for the version you have just tested.

Telugu uses Google.te-IN-Standard-A for speech and googlev2_short with te-IN for recognition. English uses your working Polly.Joanna voice and en-IN recognition. Trial account eligibility, language/model support, network latency and remaining quota can affect the live test. This does not upgrade accounts or enable billing. It is not unlimited free telephony.

## Troubleshooting

- "Server not reachable": check that bilingual_server.py (not demo_server.py) and ngrok are running in separate terminals, and the public domain matches your saved settings.
- Wrong/no language key: the menu repeats once, then ends. Start a fresh call.
- Telugu playback error before language selection: save the Twilio error code only and return to the English fallback below. The menu itself contains Telugu TTS, so test it early.
- No Telugu speech captured: ensure you selected 2, wait for the question, then say one short sentence in a quiet place. Report the error code or short server error, not secret URLs.
- Speech understood incorrectly: say కాదు or No; retry with a clear crop name and kilograms. Unsupported crops and missing quantities are not invented.
- Slow AI: the server polls in short callbacks and keeps the existing callback budget. The language menu uses an extra callback; very slow responses may reach the trial step limit. No automatic extra calls are sent.
- Unknown call outcome: inspect recent calls before retrying, as in the previous troubleshooting steps.

## English fallback

Stop bilingual_server.py with Ctrl+C. Restart:

```powershell
.\.venv\Scripts\python.exe demo_server.py
```

Then use your original call command:

```powershell
.\.venv\Scripts\python.exe demo_call.py --consent-confirmed
```

The new call launcher checks for the bilingual server so you cannot accidentally use the wrong server.

## Optional local tests and status

```powershell
.\.venv\Scripts\python.exe -m unittest test_bilingual -v
.\.venv\Scripts\python.exe bilingual_status.py
```

Offline tests do not call Twilio or Gemini. Status is read-only. SMS is still optional and uses your existing setting plus explicit caller consent. Telugu SMS uses Unicode and can take more SMS segments. It has not been live-tested here.

## Data and security

Separate local state: bilingual_calls.db. Never publish this file, saved credential files, or URLs containing the per-call token. Add bilingual_calls.db* to your project's .gitignore before sharing source. The DB contains test phone numbers and harvest details, with rows older than 24 hours cleaned at startup. Language is stored per call. Authentication is retained: allowlist, expiring per-call token, bound CallSid/account, plus signature validation when supplied. Tokens are not proof of a Twilio signature. Keep the ngrok URL private. Gemini receives crop speech text and previous crop fields, not phone numbers. Use fictional harvest details for free-tier demos.

## Sources checked

- https://www.twilio.com/docs/voice/twiml/gather
- https://www.twilio.com/docs/usage/trials/try-out-voice
- https://github.com/twilio/twilio-java/blob/master/src/main/java/com/twilio/twiml/voice/Say.java
- https://docs.cloud.google.com/speech-to-text/docs/speech-to-text-supported-languages
- https://ai.google.dev/gemini-api/docs/pricing
