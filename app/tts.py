"""Server-only ElevenLabs speech; credentials and upstream errors stay private."""
import os
import httpx


def settings():
    return (os.getenv('ELEVENLABS_VOICE_ID', 'cnc9FDcyBlbzxv28zGEM'),
            os.getenv('ELEVENLABS_MODEL_ID', 'eleven_v4'))


def synthesize(text: str) -> bytes:
    key = os.getenv('ELEVENLABS_API_KEY', '').strip()
    if not key or key == 'replace_with_your_elevenlabs_api_key':
        raise RuntimeError('Tutor audio is not configured yet.')
    if not text.strip() or len(text) > 2000:
        raise RuntimeError('This reply cannot be spoken.')
    voice, model = settings()
    try:
        response = httpx.post(
            'https://api.elevenlabs.io/v1/text-to-dialogue',
            params={'output_format': 'mp3_44100_128'},
            headers={'xi-api-key': key, 'Accept': 'audio/mpeg'},
            json={'inputs': [{'text': text, 'voice_id': voice}], 'model_id': model},
            timeout=60,
        )
        if response.status_code == 402:
            raise SpeechAccessError('This ElevenLabs voice requires a paid plan for API playback. Upgrade the ElevenLabs account or configure a voice available on your plan.')
        if response.status_code == 401:
            raise SpeechAccessError('ElevenLabs rejected the API key. Check ELEVENLABS_API_KEY on the backend and restart it.')
        if response.status_code == 429:
            raise SpeechAccessError('ElevenLabs usage limit reached. Try audio again later or check your account quota.')
        response.raise_for_status()
        if not response.headers.get('content-type', '').startswith('audio/') or not response.content:
            raise ValueError('Invalid audio')
        if len(response.content) > 5_000_000:
            raise ValueError('Audio too large')
        return response.content
    except SpeechAccessError:
        raise
    except Exception:
        raise RuntimeError('Tutor audio is unavailable. Tap replay to try again.') from None


class SpeechAccessError(RuntimeError):
    """Fixed, user-safe provider configuration messages."""
