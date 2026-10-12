import pytest
from app.runtime import validate_runtime
from app.provider import make_provider, HFSpaceProvider, OllamaProvider


def test_remote_default(monkeypatch):
    monkeypatch.delenv('PARROT_PROVIDER', raising=False)
    assert isinstance(make_provider(), HFSpaceProvider)


@pytest.mark.parametrize('variable,value', [('PARROT_PROVIDER','ollama'), ('PARROT_ASR_PROVIDER','local'), ('PARROT_ASR_PROVIDER','whisper')])
def test_container_rejects_local_inference(monkeypatch, variable, value):
    monkeypatch.setenv('PARROT_REMOTE_ONLY','1')
    monkeypatch.setenv('PARROT_PROVIDER','hf_space')
    monkeypatch.setenv('PARROT_ASR_PROVIDER','hf_space')
    monkeypatch.setenv(variable,value)
    with pytest.raises(RuntimeError, match='Remote-only'):
        validate_runtime()


def test_explicit_local_development_allowed(monkeypatch):
    monkeypatch.setenv('PARROT_REMOTE_ONLY','0')
    monkeypatch.setenv('PARROT_PROVIDER','ollama')
    validate_runtime()
    assert isinstance(make_provider(), OllamaProvider)
