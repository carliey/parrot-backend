"""Local inference for the official NCAIR Hausa ASR checkpoint."""

import os
import subprocess
import threading

MODEL_ID = 'NCAIR1/Hausa-ASR'
_pipe = None
_load_lock = threading.Lock()


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


def transcribe(audio: bytes) -> str:
    import numpy as np

    # ffmpeg decodes Expo's compressed recording without keeping raw audio on disk.
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
    output = _pipeline()({'array': samples.copy(), 'sampling_rate': 16000},
                         generate_kwargs={'language': 'ha', 'task': 'transcribe'})
    return output['text'].strip()
