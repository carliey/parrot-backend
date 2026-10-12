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

class HFSpaceProvider:
    mode = 'real'

    def __init__(self):
        self.space = os.getenv('PARROT_GENERATION_SPACE', 'phaeeza/parrot-ai')
        self.version = 'NCAIR1/N-ATLaS; Transformers BF16; ' + self.space
        self.timeout = float(os.getenv('PARROT_GENERATION_TIMEOUT_SECONDS', '180'))
        self._client = None

    def client(self):
        if self._client is None:
            from gradio_client import Client
            token = os.getenv('HF_TOKEN', '').strip()
            if not token or token == 'hf_replace_with_your_token':
                raise RuntimeError('Set HF_TOKEN on the backend for hosted generation')
            self._client = Client(self.space, token=token, verbose=False,
                                  analytics_enabled=False, httpx_kwargs={'timeout': 30})
        return self._client

    def ready(self) -> bool:
        job = None
        try:
            job = self.client().submit(api_name='/model_info')
            info = job.result(timeout=30)
            return (isinstance(info, dict) and info.get('ready') is True
                    and info.get('model_id') == 'NCAIR1/N-ATLaS'
                    and info.get('contract_version') == 1)
        except Exception:
            if job is not None:
                job.cancel()
            return False

    def generate(self, messages, max_tokens=80, format_schema=None) -> str:
        job = None
        try:
            messages = [dict(message) for message in messages]
            if format_schema and max_tokens >= 400:
                instruction = (
                    ' Return exactly one compact JSON object matching this schema. '
                    'No markdown, explanation or trailing text. Keep evidence brief '
                    'and include each skill at most once. JSON schema: '
                    + json.dumps(format_schema, ensure_ascii=False, separators=(',', ':')))
                if messages and messages[0]['role'] == 'system':
                    messages[0]['content'] += instruction
                else:
                    messages.insert(0, {'role': 'system', 'content': instruction.strip()})
            job = self.client().submit(
                messages_json=json.dumps(messages, ensure_ascii=False),
                max_tokens=600 if format_schema and max_tokens >= 400 else max_tokens,
                format_schema_json=json.dumps(format_schema) if format_schema else '',
                api_name='/generate_response')
            result = job.result(timeout=self.timeout)
            if not isinstance(result, str) or not result.strip():
                raise ValueError('Invalid generation response')
            return result.strip()
        except Exception:
            if job is not None:
                job.cancel()
            raise RuntimeError('Hosted tutor unavailable. Check Space status, access and GPU quota.') from None


def make_provider() -> Provider:
    mode = os.getenv('PARROT_PROVIDER', 'ollama')
    if mode == 'ollama': return OllamaProvider()
    if mode == 'hf_space': return HFSpaceProvider()
    raise ValueError('PARROT_PROVIDER must be ollama or hf_space')
