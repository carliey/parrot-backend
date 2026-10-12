# Deploy the backend on Dokploy

This CPU-only image calls two Hugging Face Spaces. It installs neither Ollama,
PyTorch, Transformers nor model weights. huggingface-hub and gradio-client are
HTTP client libraries, not local inference engines. ffmpeg only converts uploads.
There is no automatic fallback to local inference when a Space is unavailable.
The image's remote-only startup check rejects local provider settings.

## Steps

1. Push the backend code, Dockerfile and requirements-runtime.txt to your Git
   repository. Never commit `.env`, keys or `parrot.sqlite3`.
2. In Dokploy, open/create your project and add an **Application**. Connect the
   Git repository and select the branch containing these files.
3. Select the **Dockerfile** build type. If the repository is the backend folder,
   use Dockerfile path `Dockerfile` and build context `.`. If the repository holds
   both projects, use path `parrot-backend/Dockerfile` and context `parrot-backend`.
4. Under **Environment**, copy the contents of `deploy/dokploy.env.example`.
   Replace HF_TOKEN and ELEVENLABS_API_KEY placeholders with their actual values,
   and save. These are runtime variables, not build arguments. The existing
   ElevenLabs library voice requires a paid account for API use.
5. Under **Advanced → Volumes/Mounts**, add a named **Volume** called
   `parrot-data`, mounted at `/data`. Save. A new Docker volume inherits the
   image directory's ownership (UID 10001). An existing/bind-mounted directory
   must be writable by UID 10001. Keep one replica and one Uvicorn worker.
6. Under **Domains**, add your backend hostname, target container port **8000**,
   and enable HTTPS. Point that hostname's DNS at your Dokploy server. You do not
   need a publicly published raw port 8000 when using Dokploy's domain routing.
7. Click **Deploy**, then open the deployment and runtime logs. The server should
   start without downloading model weights. Do not use requirements-speech.txt.
8. Open `https://YOUR-HOST/health`; expect `{"status":"alive"}`. Open `/ready`;
   expect `ready: true` and the HF Space model version. Readiness checks model
   metadata; it does not prove GPU quota or successful generation. Test one real
   session, recording, reply and feedback before shutting down your old backend.
9. In `parrot-mobile/.env`, set `EXPO_PUBLIC_API_URL=https://YOUR-HOST` with no
   trailing slash. Restart Expo and reload the development app. For an installed
   release APK, rebuild and reinstall it: its API address is bundled at build time.

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

## Local Docker check

From parrot-backend:

```sh
docker build -t parrot-backend .
docker run --rm --name parrot-backend -p 8000:8000 --env-file .env \
  -e PARROT_REMOTE_ONLY=1 -e PARROT_PROVIDER=hf_space -e PARROT_ASR_PROVIDER=hf_space \
  -e PARROT_DB=/data/parrot.sqlite3 -v parrot-data:/data parrot-backend
```

Official reference: https://docs.dokploy.com/docs/core/applications
