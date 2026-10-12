---
title: Parrot N-ATLaS
emoji: 🦜
colorFrom: green
colorTo: blue
sdk: gradio
sdk_version: 5.49.1
python_version: 3.12.12
app_file: app.py
pinned: false
---

# Parrot N-ATLaS generation

Runs the official gated `NCAIR1/N-ATLaS` model in BF16 using Transformers on
ZeroGPU. This is not the quantized Ollama GGUF runtime. The backend continues
to own lessons, validation, history, ASR integration and interaction logging.

## Deploy

1. In `phaeeza/parrot-ai`, keep Gradio and ZeroGPU selected.
2. Ensure the account owning the token has accepted access to `NCAIR1/N-ATLaS`.
3. Under Settings → Variables and secrets, add **secret** `HF_TOKEN` with model
   read access. Never put the token in these files.
4. Upload `README.md`, `app.py`, and `requirements.txt` from this folder to the
   Space repository root, replacing the blank template files. Commit the upload.
5. Wait for the build and model download. Check the runtime logs if startup fails.
6. In the app, click Check status, then Generate. A real GPU generation test is
   required before switching the backend. Cold starts and GPU queues take time.

The API is Gradio, not a bare FastAPI POST route. The backend uses gradio_client
and calls `/generate_response` with messages_json, max_tokens and
format_schema_json. `/model_info` does not request GPU time.

## Connect the backend

Keep HF_TOKEN in the backend's private `.env` as well, with access to this Space.
After the Space works, set:

```dotenv
PARROT_PROVIDER=hf_space
PARROT_GENERATION_SPACE=phaeeza/parrot-ai
PARROT_GENERATION_TIMEOUT_SECONDS=180
```

Restart the backend and start a **new** practice session (old sessions belong to
the previous provider). Test greetings, general practice and session feedback.
ASR still uses the separate Hausa-ASR Space. No mobile code change is required.
To return to local generation, set PARROT_PROVIDER=ollama and restart.

The token used for backend requests shares that account's ZeroGPU quota across
app users. Queues/quota exhaustion can make generation unavailable. Keep this
Space private if you only want authorized backend access. Deployment of this
Space removes the local model dependency; deploy the backend separately to
remove the remaining laptop dependency. No conversation database is stored here.

Local adapter tests do not prove GPU/runtime compatibility. Verify actual hosted
generation and schema-constrained feedback after upload before using with testers.
