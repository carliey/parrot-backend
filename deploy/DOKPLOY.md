# Deploy the backend on Dokploy

This CPU-only image calls two Hugging Face Spaces. It installs neither Ollama,
PyTorch, Transformers nor model weights. huggingface-hub and gradio-client are
HTTP client libraries, not local inference engines. ffmpeg only converts uploads.
There is no automatic fallback to local inference when a Space is unavailable.
The image's remote-only startup check rejects local provider settings.

## Docker Compose deployment

1. Push `docker-compose.yml`, `Dockerfile`, `requirements-runtime.txt`, `app/`
   and the backend scripts to your Git repository. Do not push `.env` or databases.
2. In your Dokploy project, add a **Docker Compose** service. Choose standard
   **Docker Compose**, not Stack: this setup builds an image from the Dockerfile.
3. Connect your Git repository and branch. Set **Compose Path** to
   `docker-compose.yml` for a backend-only repository, or
   `parrot-backend/docker-compose.yml` if both projects share the repository.
   Use the Git source, rather than pasting only YAML into a raw Compose service:
   the build needs the Dockerfile and application source from that repository.
4. Open **Environment**. Copy `deploy/dokploy.env.example`, replace the HF_TOKEN
   and ELEVENLABS_API_KEY placeholders with your actual secrets, and save.
   Compose explicitly passes these variables to the container. It fixes both
   model providers to hf_space and the database path to `/data/parrot.sqlite3`.
5. The Compose file creates and mounts the named volume `parrot-data` at `/data`.
   Do not add another database service or manually create a duplicate mount.
   Docker prefixes the volume name with the Compose project name. Keep that
   project/service identity stable across redeployments to reuse its records.
6. Under **Domains**, add your backend hostname. Choose service **backend**, port
   **8000**, path `/`, and enable HTTPS. Point its DNS to your Dokploy server.
   Dokploy configures routing/network integration. No public host-port mapping
   is needed in this Compose file. Redeploy after domain changes.
7. Click **Deploy**. Check build and runtime logs. `/health` should return
   `{"status":"alive"}` and `/ready` should report the HF generation Space.
   Readiness is metadata-only; test a real conversation, upload and feedback too.
8. Set `EXPO_PUBLIC_API_URL=https://YOUR-HOST` in `parrot-mobile/.env`, without a
   trailing slash. Restart Expo/reload development apps; rebuild and reinstall
   release APKs to change their bundled address.

No Ollama or GPU service is created. Both Spaces must remain available. Keep one
backend instance while using SQLite and in-process concurrency controls. Enable
Dokploy Volume Backups for the named data volume. Never use `docker compose down
-v` unless you intend to delete the database and cached audio.

## Data and restarts

The volume stores sessions, consented validation records and generated speech.
Without it, replacing a container loses these records. Configure volume backups
in Dokploy. Start with a new database unless you need laptop records transferred.
To transfer them, stop writes on the laptop and server, make a SQLite backup,
copy it to `/data/parrot.sqlite3`, grant UID 10001 ownership, and restart. Do not
copy a live database or bake it into the image. Keep the app on one server/replica
while using this SQLite setup and in-process concurrency controls.

HF Space availability and account GPU quotas still apply. The container health
check uses `/health`, so a temporary HF outage doesn't trigger restart loops.

## Optional laptop Ollama

The original Ollama code remains. In the laptop backend `.env`, set:

```dotenv
PARROT_REMOTE_ONLY=0
PARROT_PROVIDER=ollama
PARROT_OLLAMA_URL=http://127.0.0.1:11434
PARROT_MODEL_ID=hf.co/QuantFactory/N-ATLaS-GGUF:Q4_K_M
PARROT_ASR_PROVIDER=hf_space
```

Start Ollama and the backend normally. Return PARROT_PROVIDER to hf_space when
finished. Local ASR is also opt-in using PARROT_ASR_PROVIDER=local and the separate
requirements-speech.txt; never select it in the deployed container.

## Local Docker Compose check

From `parrot-backend`, with credentials set in your private `.env`:

```sh
docker compose -f docker-compose.yml -f compose.local.yml config --quiet
docker compose -f docker-compose.yml -f compose.local.yml up -d --build
docker compose logs -f backend
curl http://localhost:8000/health
```

The optional local override publishes port 8000 on loopback only. Stop with
`docker compose -f docker-compose.yml -f compose.local.yml down` (without `-v`).
These commands use HF Spaces, even if your laptop `.env` selects Ollama for a
non-Docker development run. To inspect consenting records inside the deployment:

```sh
docker compose exec -T backend python export_sessions.py
```

Run deployment-side commands in the actual Compose project directory and with
Dokploy's project name, or use Dokploy's service terminal. A new server volume
starts empty; laptop records need a separate migration.

References:
- https://docs.dokploy.com/docs/core/docker-compose
- https://docs.dokploy.com/docs/core/docker-compose/domains
