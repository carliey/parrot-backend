import os, json, urllib.request
from typing import Protocol

class Provider(Protocol):
    mode: str
    version: str
    def ready(self) -> bool: ...
    def generate(self, messages: list[dict[str, str]], max_tokens: int = 80, format_schema: dict | None = None) -> str: ...

class OllamaProvider:
    mode = 'real'
    def __init__(self):
        self.model_id = os.getenv('PARROT_MODEL_ID', 'hf.co/QuantFactory/N-ATLaS-GGUF:Q4_K_M')
        self.version = self.model_id + '; Ollama GGUF Q4_K_M'
        self.url = os.getenv('PARROT_OLLAMA_URL', 'http://127.0.0.1:11434')
    def ready(self) -> bool:
        try:
            with urllib.request.urlopen(self.url + '/api/tags', timeout=2) as response:
                tags = json.load(response)['models']
            return any(m['name'].lower() == self.model_id.lower() for m in tags)
        except (OSError, KeyError, ValueError): return False
    def generate(self, messages: list[dict[str, str]], max_tokens: int = 80, format_schema: dict | None = None) -> str:
        payload = {'model': self.model_id, 'messages': messages, 'stream': False,
            'options': {'num_predict': max_tokens, 'num_ctx': 4096, 'temperature': 0 if format_schema else 0.2}}
        if format_schema: payload['format'] = format_schema
        body = json.dumps(payload).encode()
        request = urllib.request.Request(self.url + '/api/chat', body, {'Content-Type':'application/json'})
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.load(response)['message']['content'].strip()

def make_provider() -> Provider:
    mode = os.getenv('PARROT_PROVIDER', 'ollama')
    if mode == 'ollama': return OllamaProvider()
    raise ValueError('PARROT_PROVIDER must be ollama')
