"""Official Hausa ASR through a Gradio Space or the local checkpoint."""

import os
import subprocess
import threading
import tempfile
import wave
from functools import lru_cache
from pathlib import Path
from .hf_errors import HuggingFaceQuotaError, quota_error_message

MODEL_ID = 'NCAIR1/Hausa-ASR'
WHISPER_MODEL_ID = 'openai/whisper-base'
_pipe = None
_load_lock = threading.Lock()
_whisper_model = None
_whisper_lock = threading.Lock()
DEFAULT_SPACE = 'phaeeza/Hausa-tutor-conversation-voice-first'


def configured_model_id() -> str:
    return WHISPER_MODEL_ID if os.getenv('PARROT_ASR_PROVIDER', 'hf_space').strip().lower() == 'whisper' else MODEL_ID


class ASRConfigurationError(RuntimeError):
    """Safe, actionable configuration errors that may be shown to the user."""


@lru_cache(maxsize=1)
def _space_client():
    from gradio_client import Client

    token = os.getenv('HF_TOKEN', '').strip()
    if token == 'hf_replace_with_your_token':
        raise ASRConfigurationError('Replace the HF_TOKEN placeholder in parrot-backend/.env with your actual token, then restart the backend with --env-file .env')
    return Client(
        os.getenv('PARROT_ASR_SPACE', DEFAULT_SPACE), token=token or None,
        verbose=False, analytics_enabled=False,
        httpx_kwargs={'timeout': 30},
    )


def _transcribe_space(samples) -> str:
    from gradio_client import handle_file
    import numpy as np

    try:
        timeout = float(os.getenv('PARROT_ASR_TIMEOUT_SECONDS', '90'))
        if not 1 <= timeout <= 300:
            raise ValueError
    except ValueError as exc:
        raise RuntimeError('PARROT_ASR_TIMEOUT_SECONDS must be between 1 and 300') from exc

    # Gradio uploads a file; keep our temporary copy only for this request.
    with tempfile.TemporaryDirectory(prefix='parrot-asr-') as directory:
        path = Path(directory) / 'recording.wav'
        with wave.open(str(path), 'wb') as recording:
            recording.setnchannels(1)
            recording.setsampwidth(2)
            recording.setframerate(16000)
            recording.writeframes((np.clip(samples, -1, 1) * 32767).astype('<i2').tobytes())
        job = None
        try:
            client = _space_client()
            job = client.submit(
                audio=handle_file(str(path)), lesson_name='Greeting', custom_lesson='',
                api_name='/check_hausa',
            )
            output = job.result(timeout=timeout)
        except ASRConfigurationError:
            raise
        except TimeoutError as exc:
            if job is not None:
                try:
                    job.cancel()
                except Exception:
                    pass
            raise RuntimeError('Hausa ASR Space timed out; its queue may be busy. Try again shortly.') from exc
        except Exception as exc:
            # Never return remote exception text: it may contain credentials or URLs.
            quota_message = quota_error_message(exc)
            if quota_message:
                raise HuggingFaceQuotaError(quota_message) from None
            raise RuntimeError(
                'Hausa ASR Space is unavailable. Check HF_TOKEN in .env, Space status, '
                'and Hugging Face GPU quota, then retry.'
            ) from exc
    if not isinstance(output, (list, tuple)) or len(output) != 3 or not isinstance(output[0], str):
        raise RuntimeError('Hausa ASR Space returned an unexpected response')
    # The Space also returns a hardcoded lesson score and target. Ignore both.
    return output[0].strip()


def _pipeline():
    global _pipe
    with _load_lock:
        if _pipe is None:
            try:
                import torch
                from transformers import pipeline
            except ImportError as exc:
                raise RuntimeError('Install requirements-speech.txt to enable Hausa ASR') from exc
            device = 'mps' if torch.backends.mps.is_available() else 'cpu'
            try:
                _pipe = pipeline('automatic-speech-recognition', model=MODEL_ID, device=device)
            except OSError as exc:
                if 'gated repo' in str(exc).lower() or 'not in the authorized list' in str(exc).lower():
                    raise RuntimeError(
                        'Hugging Face access to NCAIR1/Hausa-ASR is not granted for this account. '
                        'Accept the model conditions on its Hugging Face page.'
                    ) from exc
                raise
        return _pipe


def _openai_whisper():
    """Load the already-downloaded OpenAI Whisper checkpoint on the laptop."""
    global _whisper_model
    with _whisper_lock:
        if _whisper_model is None:
            try:
                import torch
                import whisper
            except ImportError as exc:
                raise RuntimeError(
                    'Install local Whisper with .venv312/bin/pip install -r requirements-whisper.txt'
                ) from exc
            checkpoint = Path(os.getenv(
                'PARROT_WHISPER_CHECKPOINT',
                str(Path.home() / '.cache/whisper/base.pt'),
            )).expanduser()
            if not checkpoint.is_file():
                raise RuntimeError(
                    'Local Whisper checkpoint is missing. Set PARROT_WHISPER_CHECKPOINT '
                    'to your downloaded multilingual .pt file.'
                )
            device = 'mps' if torch.backends.mps.is_available() else 'cpu'
            _whisper_model = whisper.load_model(str(checkpoint), device=device)
        return _whisper_model


def transcribe(audio: bytes) -> str:
    import numpy as np

    # Validate Expo recordings before sending any audio to a model or remote service.
    try:
        result = subprocess.run(
            [os.getenv('PARROT_FFMPEG', 'ffmpeg'), '-nostdin', '-v', 'error',
             '-i', 'pipe:0', '-t', '31', '-ac', '1', '-ar', '16000',
             '-f', 'f32le', 'pipe:1'],
            input=audio, capture_output=True, timeout=45, check=True,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        raise ValueError('Audio could not be decoded; check ffmpeg and the recording') from exc
    samples = np.frombuffer(result.stdout, dtype='<f4')
    if len(samples) < 1600 or len(samples) > 30 * 16000:
        raise ValueError('Record between 0.1 and 30 seconds of speech')
    provider = os.getenv('PARROT_ASR_PROVIDER', 'hf_space').strip().lower()
    if provider == 'hf_space':
        return _transcribe_space(samples)
    if provider == 'whisper':
        # OpenAI Whisper accepts 16 kHz float32 samples. Keep recognition in Hausa.
        output = _openai_whisper().transcribe(
            samples.copy(), language='ha', task='transcribe', fp16=False,
            condition_on_previous_text=False,
        )
        return output['text'].strip()
    if provider != 'local':
        raise RuntimeError('PARROT_ASR_PROVIDER must be whisper, local or hf_space')
    output = _pipeline()({'array': samples.copy(), 'sampling_rate': 16000},
                         generate_kwargs={'language': 'ha', 'task': 'transcribe'})
    return output['text'].strip()
