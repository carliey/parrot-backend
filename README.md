# Parrot backend

FastAPI practice API for the Hausa app. The three guided beginner lessons—greetings, introductions, and buying things—and the combined “Put it all together” practice are defined in `app/lesson_plans.json` and awaiting language review. See [LESSON_PLANS.md](LESSON_PLANS.md) for roles, steps, reply constraints, and the editing workflow.

## Local setup

This Mac reports Apple M1 Pro, arm64 Python, 16 GB unified memory and about 160 GB free disk at inspection. N-ATLaS is a Llama 3 8B derivative. The full 16-bit weights are about 16 GB before runtime overhead, so do not load them here. The selected `QuantFactory/N-ATLaS-GGUF:Q4_K_M` card traces its quantization to `NCAIR1/N-ATLaS`; use Ollama on Metal. This is a community quantization and should be checked against its source revision before release. Direct MLX conversion from the full weights would require holding or staging the full model plus conversion output, so it was not attempted.

```
/opt/homebrew/bin/python3.12 -m venv .venv312
.venv312/bin/pip install -r requirements.txt
cp -n .env.example .env            # replace HF_TOKEN in .env before starting
ollama pull hf.co/QuantFactory/N-ATLaS-GGUF:Q4_K_M
ollama serve                       # if not already running
.venv312/bin/uvicorn app.main:app --env-file .env --host 0.0.0.0 --port 8000 --workers 1
```

Never use `--reload` or multiple workers with a local inference process. Ollama loads the quantized model on demand. `PARROT_DB` chooses the SQLite path. Do not commit `.env`, tokens or database files. If the original gated model is needed, accept its conditions at https://huggingface.co/NCAIR1/N-ATLaS and authenticate with `hf auth login`; the chosen community GGUF may not require that grant. No token is printed or stored by this app.

`GET /health` checks liveness without loading weights. `GET /ready` checks whether Ollama has the configured model. `GET /lessons` returns three draft lessons and the combined practice. OpenAPI is at `/docs`.

```
curl http://localhost:8000/health
curl -X POST http://localhost:8000/sessions -H 'Content-Type: application/json' -d '{"topic":"greetings","consent":false}'
# Use session_id and access_token from the response:
curl -X POST http://localhost:8000/sessions/SESSION_ID/turns -H 'Authorization: Bearer ACCESS_TOKEN' -H 'Content-Type: application/json' -d '{"turn_id":"turn-1","text":"Sannu"}'
curl -X POST http://localhost:8000/sessions/SESSION_ID/finish -H 'Authorization: Bearer ACCESS_TOKEN'
```

Start and turn responses include `lesson_progress`: completed and total steps, completion status, the current task, and its Hausa/English hint. Unrecognized or off-step input returns 422 with `lesson_step_expected`; it does not advance the lesson. Combined practice (`general-practice`) accepts taught phrases in any order, counts each required skill once, and tolerates the documented ASR variants and fillers. Start a new session after a lesson-version update.

A start response contains `session_id`, opaque `access_token`, `provider_mode`, and `initial_tutor_message`. A turn response contains `turn_id`, `tutor_response`, `processing_ms`, and `provider_mode`. Finish returns structured feedback or insufficient evidence. The token is required on both turn and finish calls. Retries must reuse the same turn ID and text. A different text with the same ID returns 409. A failed generation records an error without a successful reply and can be retried. HTTP timeouts may not stop generation already running in Ollama.

Run tests with `.venv312/bin/pytest -q`. Export consenting real sessions only with `.venv312/bin/python export_sessions.py > real-sessions.jsonl`. Export is a local CLI operation, not an HTTP endpoint. `consent=false` is the default; participant IDs are optional pseudonyms. No raw audio is stored. SQLite storage is for local development and must be replaced or hardened before public deployment. Add TLS, authentication, rate limits, token expiry, data retention policy and privacy review before exposing this server publicly.

Hausa ASR can use the configured Hugging Face Space or the optional local speech runtime described below. TTS is still unavailable (`POST /speech/synthesize` returns 501); the text model does not produce audio.

## Hausa voice practice and validation

### Hugging Face Space (configured in .env.example)

Copy `.env.example` to `.env` and replace `HF_TOKEN=hf_replace_with_your_token` in **.env only**. The actual token must never go in the example file or mobile app. `.env` is ignored by Git. Start Uvicorn with `--env-file .env` as shown above; a plain Uvicorn command does not load this file automatically. Existing shell environment variables take precedence over values in this file.

`PARROT_ASR_PROVIDER=hf_space` uses `phaeeza/Hausa-tutor-conversation-voice-first` and its `/check_hausa` API. The backend validates the audio with ffmpeg, uploads a temporary 16 kHz mono WAV, and uses only the returned transcription. The Space's hardcoded score and target lesson are ignored. No local Torch/Transformers install or ASR model download is needed for this mode. `ffmpeg` must still be on PATH (on this Mac: `brew install ffmpeg` if missing).

The token authenticates requests to the Space; ZeroGPU quota is associated with the authenticated account. Space errors and quota failures return HTTP 503 without a fabricated transcript. `PARROT_ASR_TIMEOUT_SECONDS=90` limits the prediction wait; connection/upload requests have a separate 30-second network timeout. A timeout requests cancellation, but does not guarantee that remote computation stops immediately. The Space must remain available and keep its existing three-output `/check_hausa` contract. The default provider without environment configuration is still `local`.

Recordings leave your backend and are uploaded to your partner's Hugging Face Space. The temporary backend WAV is deleted after success or failure. Hugging Face/Gradio may cache the uploaded file remotely; configure retention on the Space before collecting participant recordings. N-ATLaS still runs through your local Ollama instance, so keep it running. The mobile app needs no API changes: it continues to call your backend.

### Optional local ASR

Set `PARROT_ASR_PROVIDER=local` and install `.venv312/bin/pip install -r requirements-speech.txt`. Accept the conditions for [NCAIR1/Hausa-ASR](https://huggingface.co/NCAIR1/Hausa-ASR) on Hugging Face, then authenticate this environment with `.venv312/bin/hf auth login` (or set `HF_TOKEN` in `.env`). The first voice request downloads and loads the official Whisper Small checkpoint; later requests reuse it.

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
