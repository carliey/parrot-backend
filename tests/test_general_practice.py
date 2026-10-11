import json
import pytest

from app import main
from app.general_practice import REPAIR_REPLIES, validate_response
from app.lessons import progress
from app.store import Store
from test_api import client, create


def response(reply='Yauwa', skills=None, status='understood'):
    return json.dumps({'reply': reply, 'skills': skills or [], 'status': status})


def send(client, session, auth, text, turn_id='one'):
    return client.post(f"/sessions/{session['session_id']}/turns", headers=auth,
                       json={'turn_id': turn_id, 'text': text})


def test_combined_utterance_counts_two_skills_and_replays_original_state(client, monkeypatch):
    calls = []
    def generate(messages, *_):
        calls.append(messages)
        return response('Yauwa. Lafiya lau.', [
            {'skill': 'greet', 'evidence': 'Saanu'}, {'skill': 'time', 'evidence': 'ina kwana'}])
    monkeypatch.setattr(main.provider, 'generate', generate)
    session, auth = create(client, 'general-practice', consent=True)
    first = send(client, session, auth, 'Saanu, ina kwana?')
    assert first.status_code == 200
    assert first.json()['lesson_progress']['completed_steps'] == 2
    send(client, session, auth, 'Saanu, ina kwana?', 'two')
    assert send(client, session, auth, 'Saanu, ina kwana?').json() == first.json()
    assert len(calls) == 2
    exported = list(main.store.export())[0]['turns'][0]
    assert exported['learner_text'] == 'Saanu, ina kwana?'
    assert len(exported['skill_evidence']) == 2
    assert exported['conversation_status'] == 'understood'


def test_semantic_paraphrase_gets_reply_without_exact_match(client, monkeypatch):
    monkeypatch.setattr(main.provider, 'generate', lambda *_: response('Na gode.', [
        {'skill': 'request', 'evidence': 'Ba ni wannan'}]))
    session, auth = create(client, 'general-practice')
    result = send(client, session, auth, 'Toh, Ba ni wannan')
    assert result.status_code == 200
    assert result.json()['lesson_progress']['completed_steps'] == 1


@pytest.mark.parametrize('status,text', [('unclear', 'mmm ah'), ('off_topic', 'Teach me politics')])
def test_support_reply_does_not_award_skills(client, monkeypatch, status, text):
    monkeypatch.setattr(main.provider, 'generate', lambda *_: response(REPAIR_REPLIES[status], [
        {'skill': 'greet', 'evidence': text}], status))
    session, auth = create(client, 'general-practice')
    result = send(client, session, auth, text)
    assert result.status_code == 200
    assert result.json()['tutor_response'] == REPAIR_REPLIES[status]
    assert result.json()['lesson_progress']['completed_steps'] == 0


def test_skill_evidence_must_be_current_and_relevant():
    _, _, skills = validate_response(response('Yauwa', [
        {'skill': 'name', 'evidence': 'Suna na Amina'},  # older, not current
        {'skill': 'request', 'evidence': 'Sannu'},  # known different skill
        {'skill': 'invented', 'evidence': 'Sannu'},
    ]), 'Sannu', [{'learner_text': 'Suna na Amina', 'tutor_text': 'Sannu'}])
    assert skills == [{'skill': 'greet', 'evidence': 'Sannu'}]


@pytest.mark.parametrize('reply', [
    'Yauwa. Sannu. Na gode.', 'Ina kwana? Kai fa?', '₦500', 'Ya kake?', 'Yaya kike?',
    'An extensive exposition regarding economics and parliamentary governance.', 'Sannu\nYauwa',
    ' '.join(['Sannu'] * 21), '',
])
def test_reply_limits(reply):
    with pytest.raises(ValueError):
        validate_response(response(reply), 'Sannu', [])


def test_context_is_forwarded_and_replies_are_not_an_enum(client, monkeypatch):
    calls = []
    def generate(messages, _, schema):
        calls.append(messages)
        assert 'enum' not in schema.get('anyOf', [schema])[0]['properties']['reply']
        if messages[-1]['content'] == 'Kai fa?':
            return response('Lafiya lau.')
        return response('Lafiya lau. Kai fa?')
    monkeypatch.setattr(main.provider, 'generate', generate)
    session, auth = create(client, 'general-practice')
    send(client, session, auth, 'Ya kake?')
    result = send(client, session, auth, 'Kai fa?', 'two')
    assert result.status_code == 200
    assert result.json()['lesson_progress']['completed_steps'] == 1
    assert {'role': 'user', 'content': 'Ya kake?'} in calls[-1]
    assert {'role': 'assistant', 'content': 'Lafiya lau. Kai fa?'} in calls[-1]


def test_complete_skills_do_not_end_conversation_and_survive_reopening(client, monkeypatch):
    session, auth = create(client, 'general-practice')
    for i, text in enumerate(['sannu', 'ina yini', 'ya kake', 'sunana Amina',
                              'ya sunanka', 'nawa ne wannan', 'toh bani', 'nagode']):
        result = send(client, session, auth, text, str(i))
        assert result.status_code == 200
    assert result.json()['lesson_progress']['complete']
    assert send(client, session, auth, 'Madallah', 'extra').status_code == 200
    monkeypatch.setattr(main, 'store', Store(main.store.path))
    with main.store.connect() as db:
        state = progress('general-practice', main.store.turns(db, session['session_id']))
    assert state['completed_steps'] == 8
    assert 'Keep chatting' in state['instruction']
    assert client.post(f"/sessions/{session['session_id']}/finish", headers=auth).status_code == 200
    assert send(client, session, auth, 'Sannu', 'finished').status_code == 409


def test_invalid_model_reply_retries_without_persisting_skills(client, monkeypatch):
    calls = []
    def generate(*_):
        calls.append(1)
        return response('₦999', [{'skill': 'price', 'evidence': 'Nawa ne wannan?'}])
    monkeypatch.setattr(main.provider, 'generate', generate)
    session, auth = create(client, 'general-practice')
    assert send(client, session, auth, 'Nawa ne wannan?').status_code == 503
    assert len(calls) == 2
    with main.store.connect() as db:
        assert progress('general-practice', main.store.turns(db, session['session_id']))['completed_steps'] == 0
        assert db.execute('SELECT count(*) FROM turn_assessments').fetchone()[0] == 0


def test_recover_combined_variants_when_model_omits_skills():
    _, _, skills = validate_response(response('Yauwa. Lafiya lau.'), 'Saanu, ina kwana?', [])
    assert {s['skill'] for s in skills} == {'greet', 'time'}
    _, _, skills = validate_response(response('Na gode'), 'Toh, ba ni wannan. Nagode.', [])
    assert {s['skill'] for s in skills} == {'request', 'thanks'}


def test_polite_price_is_not_a_purchase_request():
    _, _, skills = validate_response(response('₦200', [
        {'skill': 'price', 'evidence': 'Nawa ne wannan don Allah?'},
        {'skill': 'request', 'evidence': 'Nawa ne wannan don Allah?'},
    ]), 'Nawa ne wannan don Allah?', [])
    assert {s['skill'] for s in skills} == {'price'}


def test_reciprocal_name_skill_requires_name_context():
    raw = response('Lafiya lau', [{'skill': 'ask-name', 'evidence': 'Kai fa?'}])
    _, _, skills = validate_response(raw, 'Kai fa?', [{'learner_text': 'Ya kake?', 'tutor_text': 'Lafiya lau'}])
    assert skills == []
    _, _, skills = validate_response(response('Suna na Musa'), 'Suna na Amina, kai fa?', [])
    assert {s['skill'] for s in skills} == {'name', 'ask-name'}


@pytest.mark.parametrize('learner,reply,rows', [
    ('Kai fa?', 'Suna na Musa', [{'learner_text': 'Ya kake?', 'tutor_text': 'Lafiya lau'}]),
    ('Suna na Amina, kai fa?', 'Suna na Musa. Kai fa?', []),
    ('Nawa ne wannan don Allah?', 'Nawa ne wannan? ₦200', []),
    ('Sannu', 'Yauwa. Yauwa.', []),
])
def test_conversation_does_not_repeat_questions_or_switch_referent(learner, reply, rows):
    with pytest.raises(ValueError):
        validate_response(response(reply), learner, rows)
