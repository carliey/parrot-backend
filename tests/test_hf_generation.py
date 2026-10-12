import json
from unittest.mock import Mock

import pytest

from app.provider import HFSpaceProvider, make_provider


def configured(result):
    provider = HFSpaceProvider()
    provider._client = Mock()
    provider._client.submit.return_value.result.return_value = result
    return provider


def test_forwards_full_schema_and_history():
    provider = configured(' {"reply":"Yauwa"} ')
    schema = {'anyOf': [{'type': 'object', 'properties': {'reply': {'enum': ['Yauwa']}}}]}
    messages = [{'role': 'system', 'content': 'Lesson rules'}, {'role': 'user', 'content': 'Sannu'}]
    assert provider.generate(messages, 400, schema) == '{"reply":"Yauwa"}'
    kwargs = provider._client.submit.call_args.kwargs
    sent = json.loads(kwargs['messages_json'])
    assert sent[1:] == messages[1:]
    assert sent[0]['content'].startswith('Lesson rules')
    assert 'JSON schema:' in sent[0]['content']
    assert messages[0]['content'] == 'Lesson rules'
    assert json.loads(kwargs['format_schema_json']) == schema
    assert kwargs['max_tokens'] == 600
    assert kwargs['api_name'] == '/generate_response'


@pytest.mark.parametrize('response', [None, {}, '', ['hello']])
def test_invalid_remote_output_fails(response):
    provider = configured(response)
    with pytest.raises(RuntimeError, match='Hosted tutor unavailable'):
        provider.generate([])


def test_remote_errors_are_sanitized_and_job_cancelled():
    provider = configured(None)
    job = provider._client.submit.return_value
    job.result.side_effect = TimeoutError('secret token and private prompt')
    with pytest.raises(RuntimeError) as error:
        provider.generate([])
    assert 'secret' not in str(error.value)
    job.cancel.assert_called_once()


def test_readiness_checks_model_and_contract_without_generation():
    provider = configured({'ready': True, 'model_id': 'NCAIR1/N-ATLaS', 'contract_version': 1})
    assert provider.ready()
    provider._client.submit.assert_called_once_with(api_name='/model_info')
    provider._client.submit.return_value.result.return_value['model_id'] = 'another-model'
    assert not provider.ready()


def test_provider_selection(monkeypatch):
    monkeypatch.setenv('PARROT_PROVIDER', 'hf_space')
    assert isinstance(make_provider(), HFSpaceProvider)
