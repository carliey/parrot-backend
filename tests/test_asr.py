import io
import wave
from pathlib import Path

import pytest

from app import asr


def recording(seconds=0.25):
    data = io.BytesIO()
    with wave.open(data, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b'\x00\x00' * int(8000 * seconds))
    return data.getvalue()


@pytest.fixture
def space(monkeypatch):
    monkeypatch.setenv('PARROT_ASR_PROVIDER', 'hf_space')
    monkeypatch.setenv('PARROT_ASR_TIMEOUT_SECONDS', '90')
    state = {'output': (' ina kwana? ', '60% hardcoded', 'Sannu ya kake?')}

    class Job:
        def result(self, timeout):
            assert timeout == 90
            if 'error' in state:
                raise state['error']
            return state['output']

        def cancel(self):
            state['cancelled'] = True

    class Client:
        def submit(self, **kwargs):
            state['path'] = Path(kwargs['audio']['path'])
            assert kwargs['api_name'] == '/check_hausa'
            with wave.open(str(state['path'])) as wav:
                assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (16000, 1, 2)
                assert wav.getnframes() == 4000
            return Job()

    monkeypatch.setattr(asr, '_space_client', lambda: Client())
    monkeypatch.setattr(asr, '_pipeline', lambda: pytest.fail('Remote ASR must not load local weights'))
    return state


def test_upload_converts_audio_uses_transcript_and_cleans_up(space):
    assert asr.transcribe(recording()) == 'ina kwana?'
    assert not space['path'].exists()


def test_remote_failure_is_sanitized_and_cleans_up(space):
    space['error'] = ValueError('Authorization: Bearer hf_secret_test')
    with pytest.raises(RuntimeError) as error:
        asr.transcribe(recording())
    assert 'hf_secret_test' not in str(error.value)
    assert 'HF_TOKEN' in str(error.value)
    assert not space['path'].exists()


def test_queue_timeout_cancels_and_cleans_up(space):
    space['error'] = TimeoutError()
    with pytest.raises(RuntimeError, match='timed out'):
        asr.transcribe(recording())
    assert space['cancelled']
    assert not space['path'].exists()


def test_placeholder_token_error_remains_actionable(monkeypatch):
    monkeypatch.setenv('PARROT_ASR_PROVIDER', 'hf_space')
    monkeypatch.setenv('HF_TOKEN', 'hf_replace_with_your_token')
    asr._space_client.cache_clear()
    try:
        with pytest.raises(asr.ASRConfigurationError, match='parrot-backend/.env'):
            asr.transcribe(recording())
    finally:
        asr._space_client.cache_clear()


@pytest.mark.parametrize('output', [None, 'not a tuple', (42, 'score', 'target')])
def test_remote_contract_error_is_not_transcription(space, output):
    space['output'] = output
    with pytest.raises(RuntimeError, match='unexpected response'):
        asr.transcribe(recording())
    assert not space['path'].exists()


@pytest.mark.parametrize('audio', [b'not audio', recording(0.05), recording(30.5)],
                         ids=['invalid', 'too-short', 'too-long'])
def test_invalid_audio_is_rejected_before_upload(space, audio):
    with pytest.raises(ValueError):
        asr.transcribe(audio)
    assert 'path' not in space
