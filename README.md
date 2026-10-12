# Parrot backend

FastAPI practice API for the Hausa app. The three guided beginner lessons—greetings, introductions, and buying things—and the combined “Put it all together” practice are defined in `app/lesson_plans.json` and awaiting language review. See [LESSON_PLANS.md](LESSON_PLANS.md) for roles, steps, reply constraints, and the editing workflow.

## Hosted setup (default)

Generation and transcription use the configured HF Spaces. No model is downloaded
by the backend. For Docker and Dokploy, follow [the deployment guide](deploy/DOKPLOY.md)
and use [the environment template](deploy/dokploy.env.example).

For laptop testing against the same remote services:

```
/opt/homebrew/bin/python3.12 -m venv .venv312
.venv312/bin/pip install -r requirements.txt
cp -n .env.example .env            # replace HF_TOKEN in .env before starting
.venv312/bin/uvicorn app.main:app --env-file .env --host 0.0.0.0 --port 8000 --workers 1
```

Never use `--reload` or multiple workers with a local inference process. Ollama loads the quantized model on demand. `PARROT_DB` chooses the SQLite path. Do not commit `.env`, tokens or database files. If the original gated model is needed, accept its conditions at https://huggingface.co/NCAIR1/N-ATLaS and authenticate with `hf auth login`; the chosen community GGUF may not require that grant. No token is printed or stored by this app.

`GET /health` checks liveness without loading weights. `GET /ready` checks the configured generation provider metadata. `GET /lessons` returns three draft lessons and the combined practice. OpenAPI is at `/docs`.

```
curl http://localhost:8000/health
curl -X POST http://localhost:8000/sessions -H 'Content-Type: application/json' -d '{"topic":"greetings","consent":false}'
# Use session_id and access_token from the response:
curl -X POST http://localhost:8000/sessions/SESSION_ID/turns -H 'Authorization: Bearer ACCESS_TOKEN' -H 'Content-Type: application/json' -d '{"turn_id":"turn-1","text":"Sannu"}'
curl -X POST http://localhost:8000/sessions/SESSION_ID/finish -H 'Authorization: Bearer ACCESS_TOKEN'
```

Start and turn responses include `lesson_progress`: completed and total steps, completion status, the current task, and its Hausa/English hint. Unrecognized or off-step input returns 422 with `lesson_step_expected`; it does not advance the lesson. Combined practice (`general-practice`) accepts taught phrases in any order, counts each required skill once, and tolerates the documented ASR variants and fillers. Start a new session after a lesson-version update.

A start response contains `session_id`, opaque `access_token`, `provider_mode`, and `initial_tutor_message`. A turn response contains `turn_id`, `tutor_response`, `processing_ms`, and `provider_mode`. Finish returns structured feedback or insufficient evidence. The token is required on both turn and finish calls. Retries must reuse the same turn ID and text. A different text with the same ID returns 409. A failed generation records an error without a successful reply and can be retried. HTTP timeouts may not stop generation already running in Ollama.

Run tests with `.venv312/bin/pytest -q`. Export consenting real sessions only with `.venv312/bin/python export_sessions.py > real-sessions.jsonl`. Export is a local CLI operation, not an HTTP endpoint. `consent=false` is the default; participant IDs are optional pseudonyms. Uploaded learner recordings are deleted after processing; generated tutor speech is cached in SQLite. Use the documented persistent volume and single-replica deployment. Add TLS, authentication, rate limits, token expiry, data retention policy and privacy review before exposing this server publicly.

Hausa ASR can use the configured Hugging Face Space or the optional local speech runtime described below. Mixed-practice TTS uses ElevenLabs through the authenticated session speech endpoint; guided chats use bundled recordings. The legacy `/speech/synthesize` endpoint is unused.

## Hausa voice practice and validation

### Hugging Face Space (configured in .env.example)

Copy `.env.example` to `.env` and replace `HF_TOKEN=hf_replace_with_your_token` in **.env only**. The actual token must never go in the example file or mobile app. `.env` is ignored by Git. Start Uvicorn with `--env-file .env` as shown above; a plain Uvicorn command does not load this file automatically. Existing shell environment variables take precedence over values in this file.

`PARROT_ASR_PROVIDER=hf_space` uses `phaeeza/Hausa-tutor-conversation-voice-first` and its `/check_hausa` API. The backend validates the audio with ffmpeg, uploads a temporary 16 kHz mono WAV, and uses only the returned transcription. The Space's hardcoded score and target lesson are ignored. No local Torch/Transformers install or ASR model download is needed for this mode. `ffmpeg` must still be on PATH (on this Mac: `brew install ffmpeg` if missing).

The token authenticates requests to the Space; ZeroGPU quota is associated with the authenticated account. Space errors and quota failures return HTTP 503 without a fabricated transcript. `PARROT_ASR_TIMEOUT_SECONDS=90` limits the prediction wait; connection/upload requests have a separate 30-second network timeout. A timeout requests cancellation, but does not guarantee that remote computation stops immediately. The Space must remain available and keep its existing three-output `/check_hausa` contract. The default ASR provider is `hf_space`; local inference requires explicit opt-in.

Recordings leave your backend and are uploaded to your partner's Hugging Face Space. The temporary backend WAV is deleted after success or failure. Hugging Face/Gradio may cache the uploaded file remotely; configure retention on the Space before collecting participant recordings. N-ATLaS runs on the configured generation Space by default; Ollama is optional for laptop testing. The mobile app needs no API changes: it continues to call your backend.

### Optional local ASR

For this Mac's local development setup, install `.venv312/bin/pip install -r requirements-speech.txt`. Set `PARROT_PROVIDER=ollama` and `PARROT_ASR_PROVIDER=local` in `.env`. This selects the official `NCAIR1/Hausa-ASR` checkpoint. Keep a valid `HF_TOKEN` with model access for the first download; subsequent runs reuse the cached weights. Start Ollama, then run `.venv312/bin/uvicorn app.main:app --env-file .env --host 0.0.0.0 --port 8000 --workers 1`. Restart Uvicorn after changing `.env`; existing shell variables override the file.

Hausa ASR transcribes locally and Ollama generates the tutor reply locally, without consuming HF Space GPU quota. The phone continues to call the backend. The generic OpenAI Whisper base option remains available for experiments using `PARROT_ASR_PROVIDER=whisper`, but is no longer selected because it performed poorly on short Hausa phrases.

Docker Compose and the Dockerfile continue to select `hf_space` for generation and ASR; the laptop settings do not change Dokploy.

In real practice mode, the phone sends the recording bytes to `POST /sessions/{id}/transcriptions/{turn_id}` with the session bearer token. The backend accepts Expo's native upload content type and lets ffmpeg identify and decode the bounded audio to 16 kHz mono, runs `NCAIR1/Hausa-ASR` locally or through the Space, and returns the transcript. The phone then sends that exact transcript to the existing tutor turn endpoint with the same turn ID. The backend links the ASR model, transcript, timing, and tutor reply in the local database. No raw audio is retained on the backend, and the phone deletes its recording after the request.

For real user validation, ask each participant for a pseudonymous tester code such as `P01` and optional consent to export their text transcript. Use distinct codes for distinct people; never enter names or phone numbers. Only successful official-ASR plus N-ATLaS exchanges with consent appear in the evidence count. Run `.venv312/bin/python summarize_validation.py` for a summary and `.venv312/bin/python export_sessions.py > real-sessions.jsonl` for detailed consenting records. Review and redact the JSONL before sharing it; do not commit the database or raw export. The NAIC page requires at least 50 documented real interactions for Voice-First Access. A real device and real model still need an end-to-end smoke test before collecting participants.

For a physical Expo device on the same Wi-Fi, start this server with `--host 0.0.0.0` and set `EXPO_PUBLIC_API_URL=http://YOUR_MAC_LAN_IP:8000` in the mobile project. `localhost` on the phone means the phone itself. Keep this development server on a trusted network only.

## Guided lesson verification (11 October 2026)

All three guided lessons completed through FastAPI against the local N-ATLaS Ollama model: 12 constrained replies, with the market price held at ₦200. The first turn took about 7.1 seconds; subsequent turns took about 1.4–1.8 seconds. Market feedback reported the four demonstrated tasks. These were developer checks using a temporary database and consent=false, not real-user validation interactions. The current `real_smoke_api.py` follows the guided greeting sequence.

## Verified local result (7 October 2026, earlier curriculum)

The installed runtime was Ollama client 0.34.0 with `hf.co/QuantFactory/N-ATLaS-GGUF:Q4_K_M` (local Ollama ID `a7f2987f42c0`, 4.9 GB). The [quantization card](https://huggingface.co/QuantFactory/N-ATLaS-GGUF) identifies [aashish1904/N-ATLaS-GGUF](https://huggingface.co/aashish1904/N-ATLaS-GGUF), whose card identifies [NCAIR1/N-ATLaS](https://huggingface.co/NCAIR1/N-ATLaS). Repository revisions observed during this run: QuantFactory `fdc9567e20a63e8d27736d640cabe61e937befa8`, intermediate `fdc9567e20a63e8d27736d640cabe61e937befa8`, original `e294476928aca9030e924ca27bb8e085e8581273`. The conversion card does not attest the exact upstream source commit used. Pin and verify conversion provenance before production use.

`real_smoke_api.py` exercised the **real** model through FastAPI with two turns. Learner: “Sannu! Sunana Amina.” Tutor: “Yaya kike?” Learner follow-up: “Me na ce maka sunana?” Tutor: “Sunana Amina.” The follow-up retained the previous name. In that run the turn processing times were 463 ms and 501 ms, and finishing with structured feedback took 15.0 seconds. System-wide free memory was 23% before and 22% after that warm run. A prior cold run measured 6.9 seconds for the first turn and memory free percentage dropping from 43% to 21%; these are observations on this Mac only, not performance guarantees. The model sometimes repeated a prior answer, so tutor quality needs native-speaker evaluation.

The final feedback path requests a JSON schema from Ollama and validates it with Pydantic. Unsupported corrections and task claims are removed using stored learner text, conservative task markers, and the taught phrase list. This deliberately suppresses many model-suggested corrections until language review. An invalid JSON/schema result after two attempts returns 503 and leaves the session active. No numerical or pronunciation score is produced.

The virtual environment used Python 3.12 with FastAPI 0.142.2, Uvicorn 0.54.0, Pydantic 2.13.5, huggingface-hub 1.33.0, MLX 0.32.3, mlx-lm 0.32.0, Transformers 5.19.0, httpx 0.28.1, pytest 8.4.2. MLX and Transformers were installed for feasibility checks but the working inference path uses Ollama GGUF, not Torch. `hf auth whoami` in this environment reported “Not logged in”; the public quantized repository was still accessible. The gated original model would require accepting terms and authenticating this environment before direct access.

In a later run, the model produced a structurally valid but linguistically poor correction (replacing Hausa “Sannu” with English “Hello”). The correction filter now discards suggestions outside the taught phrase list. Model feedback remains provisional and needs native-speaker review.

## Conversational general practice (practice-4)

General practice now accepts combined phrases and paraphrases through N-ATLaS, with short replies and separate evidence-backed skill tracking. It continues after the checklist is complete. Guided lessons retain their ordered, constrained exercises. Restart the backend and start a new session after this update; existing sessions retain their older lesson version. Reload the mobile app (or rebuild an installed APK) to enable continued input after all skills are covered.

Run `.venv312/bin/python real_smoke_general.py` with Ollama running for a real-model check of combined greetings, introductions, a shopping paraphrase, contextual replies, unclear speech, and an off-topic instruction. It uses synthetic text, a temporary database and no export consent, so it does not count toward real-user validation.

Verified on 11 October 2026: 90 backend tests and 9 mobile tests passed. Eight real N-ATLaS text turns passed the general-practice smoke check, including combined expressions, name exchange, a polite price question, purchase plus thanks, contextual reciprocal reply, unclear input and off-topic redirection. Warm turn times were about 1.3–4.1 seconds on this Mac; this is not a hosting latency guarantee. Semantic judgements and Hausa phrasing still need native-speaker review.
# ElevenLabs voice for Putting it together

The mixed practice chat uses ElevenLabs for every tutor bubble, including the
opening. Learn-page recordings remain unchanged. Text appears before audio is
ready; playback starts automatically and each bubble offers Replay. Recording,
leaving, finishing, and backgrounding stop playback. Audio failure leaves text
usable and Replay retries speech without regenerating the tutor reply.

Setup:
1. Open `parrot-backend/.env` (not `.env.example`).
2. Set `ELEVENLABS_API_KEY` to the actual key from your ElevenLabs account.
3. Keep `ELEVENLABS_VOICE_ID=cnc9FDcyBlbzxv28zGEM` and
   `ELEVENLABS_MODEL_ID=eleven_v4`.
4. Restart the backend with the existing uvicorn command using `--env-file .env`.
5. Reload the mobile app and start Putting it together. The opening should speak;
   send a reply, then tap Replay. Try recording during playback to verify it stops.

The key stays on the backend, never in Expo public variables or the HF Space.
The voice must be available to your ElevenLabs account with API generation access.
Uses the text-to-dialogue endpoint with one voice and MP3 output. Only stored tutor
replies can be synthesized through an authenticated session; clients cannot send
arbitrary text. Generated audio is cached in SQLite `speech_audio`, keyed by session,
message, voice and model, to avoid repeated generation charges. It persists with
the database and is excluded from validation exports. Mobile cache files are deleted
when the chat screen unmounts. Tutor text is sent to ElevenLabs for synthesis.
Validate Hausa pronunciation on a device before tester rollout.
