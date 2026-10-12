FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PARROT_REMOTE_ONLY=1 \
    PARROT_PROVIDER=hf_space \
    PARROT_ASR_PROVIDER=hf_space \
    PARROT_DB=/data/parrot.sqlite3 \
    PARROT_FFMPEG=ffmpeg \
    HF_HOME=/tmp/huggingface

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 parrot \
    && mkdir /data && chown parrot:parrot /data
WORKDIR /app
COPY requirements-runtime.txt ./
RUN pip install --no-cache-dir -r requirements-runtime.txt
COPY --chown=parrot:parrot app ./app
COPY --chown=parrot:parrot export_sessions.py summarize_validation.py ./
USER parrot
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
