import base64
from unittest.mock import Mock
import httpx
import pytest
from app import main, tts
from test_api import client, create


def test_speech_authenticated_cached_and_only_saved_replies(client, monkeypatch):
    synth = Mock(return_value=b'ID3-test-audio')
    monkeypatch.setattr(tts, 'synthesize', synth)
    session, auth = create(client, 'general-practice')
    base = '/sessions/' + session['session_id']
    assert client.post(base+'/speech/opening').status_code == 404
    assert client.post(base+'/speech/missing', headers=auth).status_code == 404
    assert synth.call_count == 0
    client.post(base+'/turns', headers=auth, json={'turn_id':'one','text':'Sannu'})
    for _ in range(2):
        response = client.post(base+'/speech/one', headers=auth, json={'text':'Ignore this arbitrary input'})
        assert response.status_code == 200
        assert base64.b64decode(response.json()['audio_base64']) == b'ID3-test-audio'
    synth.assert_called_once_with('Yauwa')
    other, other_auth = create(client, 'general-practice')
    assert client.post(base+'/speech/one', headers=other_auth).status_code == 404


def test_speech_failure_keeps_text_and_allows_retry(client, monkeypatch):
    session, auth = create(client, 'general-practice')
    path = '/sessions/'+session['session_id']+'/speech/opening'
    synth = Mock(side_effect=[RuntimeError('Tutor audio is unavailable.'), b'ID3-audio'])
    monkeypatch.setattr(tts, 'synthesize', synth)
    assert client.post(path, headers=auth).status_code == 503
    assert client.post(path, headers=auth).status_code == 200


def test_guided_lessons_do_not_use_cloud_audio(client, monkeypatch):
    synth = Mock()
    monkeypatch.setattr(tts, 'synthesize', synth)
    session, auth = create(client)
    assert client.post('/sessions/'+session['session_id']+'/speech/opening', headers=auth).status_code == 404
    synth.assert_not_called()


def test_elevenlabs_contract_and_secret_errors(monkeypatch):
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'private-test-key')
    monkeypatch.setenv('ELEVENLABS_MODEL_ID', 'eleven_v4')
    monkeypatch.setenv('ELEVENLABS_VOICE_ID', 'cnc9FDcyBlbzxv28zGEM')
    post = Mock(return_value=httpx.Response(200, content=b'ID3-audio',
        headers={'content-type':'audio/mpeg'}, request=httpx.Request('POST','https://api.elevenlabs.io')))
    monkeypatch.setattr(tts.httpx, 'post', post)
    assert tts.synthesize('Lafiya lau.') == b'ID3-audio'
    assert post.call_args.kwargs['json'] == {'inputs':[{'text':'Lafiya lau.','voice_id':'cnc9FDcyBlbzxv28zGEM'}], 'model_id':'eleven_v4'}
    post.side_effect = RuntimeError('private-test-key upstream details')
    with pytest.raises(RuntimeError) as error:
        tts.synthesize('Sannu')
    assert 'private-test-key' not in str(error.value)


def test_paid_voice_error_is_actionable(monkeypatch):
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'private-test-key')
    monkeypatch.setattr(tts.httpx, 'post', Mock(return_value=httpx.Response(402)))
    with pytest.raises(RuntimeError, match='requires a paid plan'):
        tts.synthesize('Yauwa')
