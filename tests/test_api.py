import json
import pytest
from fastapi.testclient import TestClient
from app import main
from app.store import Store
from app.schemas import Feedback

class StubProvider:
    mode='real'; version='test-n-atlas'
    def ready(self): return True
    def generate(self, messages, max_tokens=80, format_schema=None):
        if format_schema:
            return json.dumps({'insufficient_evidence':False,'tasks_completed':[],
                'expressions_used':[],'corrections':[],'phrases_to_review':[],
                'message':'Practice complete.'})
        return 'Lafiya lau'

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'store', Store(str(tmp_path/'test.sqlite3')))
    monkeypatch.setattr(main, 'provider', StubProvider())
    main.locks.clear()
    return TestClient(main.app)

def create(client, topic='greetings', consent=False):
    response=client.post('/sessions',json={'topic':topic,'consent':consent})
    assert response.status_code==200
    data=response.json()
    return data, {'Authorization':f"Bearer {data['access_token']}"}

def test_health_access_and_topic(client):
    assert client.get('/health').json()=={'status':'alive'}
    assert client.post('/sessions',json={'topic':'sports'}).status_code==422
    session,auth=create(client)
    path=f"/sessions/{session['session_id']}/turns"
    assert client.post(path,json={'turn_id':'one','text':'Sannu'}).status_code==404
    assert client.post(path,headers={'Authorization':'Bearer wrong'},json={'turn_id':'one','text':'Sannu'}).status_code==404
    assert client.post(path,headers=auth,json={'turn_id':'one','text':'Sannu'}).status_code==200

def test_order_and_duplicate(client):
    session,auth=create(client);path=f"/sessions/{session['session_id']}/turns"
    first=client.post(path,headers=auth,json={'turn_id':'one','text':'Sannu'}).json()
    again=client.post(path,headers=auth,json={'turn_id':'one','text':'Sannu'}).json()
    assert first==again
    assert client.post(path,headers=auth,json={'turn_id':'one','text':'different'}).status_code==409
    assert client.post(path,headers=auth,json={'turn_id':'two','text':'Sunana Amina'}).status_code==200
    with main.store.connect() as db:
        rows=main.store.turns(db,session['session_id'])
    assert [r['turn_id'] for r in rows]==['one','two']
    finished=client.post(f"/sessions/{session['session_id']}/finish",headers=auth)
    assert finished.status_code==200
    assert finished.json()==client.post(f"/sessions/{session['session_id']}/finish",headers=auth).json()
    assert client.post(path,headers=auth,json={'turn_id':'three','text':'Hi'}).status_code==409

def test_inference_failure_not_success(client,monkeypatch):
    session,auth=create(client)
    def fail(*args,**kwargs):raise RuntimeError('boom')
    monkeypatch.setattr(main.provider,'generate',fail)
    path=f"/sessions/{session['session_id']}/turns"
    assert client.post(path,headers=auth,json={'turn_id':'one','text':'Sannu'}).status_code==503
    with main.store.connect() as db: row=main.store.turns(db,session['session_id'])[0]
    assert row['tutor_text'] is None and row['error']=='RuntimeError'
    monkeypatch.setattr(main.provider,'generate',lambda *args,**kwargs:'Lafiya lau')
    assert client.post(path,headers=auth,json={'turn_id':'one','text':'Sannu'}).json()['tutor_response']=='Lafiya lau'

def test_feedback_validation_and_export(client):
    with pytest.raises(Exception):
        Feedback.model_validate({'insufficient_evidence':False,'tasks_completed':'invented','expressions_used':[],'corrections':[],'phrases_to_review':[],'message':'x'})
    session,auth=create(client,consent=True)
    for i in range(2):client.post(f"/sessions/{session['session_id']}/turns",headers=auth,json={'turn_id':str(i),'text':'Sannu'})
    result=client.post(f"/sessions/{session['session_id']}/finish",headers=auth).json()
    assert result['feedback']['insufficient_evidence'] is False
    exported=list(main.store.export())
    assert len(exported)==1 and len(exported[0]['turns'])==2

def test_real_feedback_filters_unsupported_claims(client,monkeypatch):
    class Provider:
        mode='real';version='test-real-provider'
        def ready(self):return True
        def generate(self,messages,max_tokens=80,format_schema=None):
            if format_schema:
                return json.dumps({'insufficient_evidence':False,'tasks_completed':['greet someone','flew to Kano'],
                  'expressions_used':['Sannu','unspoken phrase'],
                  'corrections':[{'original':'Sannu','suggested':'Hello','explanation':'Use English'}],
                  'phrases_to_review':['Sannu','invented'],'message':'Perfect pronunciation!'})
            return 'Lafiya lau'
    monkeypatch.setattr(main,'provider',Provider())
    session,auth=create(client,consent=True)
    for i,text in enumerate(['Sannu','Sunana Amina']):
        assert client.post(f"/sessions/{session['session_id']}/turns",headers=auth,json={'turn_id':str(i),'text':text}).status_code==200
    response=client.post(f"/sessions/{session['session_id']}/finish",headers=auth)
    assert response.status_code==200
    feedback=response.json()['feedback']
    assert feedback['tasks_completed']==['greet someone']
    assert feedback['expressions_used']==['Sannu']
    assert feedback['corrections']==[]
    assert feedback['phrases_to_review']==['Sannu']
    assert 'pronunciation assessment was made' in feedback['message']
    exported=list(main.store.export())
    assert len(exported)==1 and exported[0]['provider_mode']=='real'
    assert 'token_hash' not in exported[0]

def test_invalid_model_feedback_returns_error(client,monkeypatch):
    class Provider:
        mode='real';version='test-real-provider'
        def ready(self):return True
        def generate(self,messages,max_tokens=80,format_schema=None):
            return 'not json' if format_schema else 'Lafiya lau'
    monkeypatch.setattr(main,'provider',Provider())
    session,auth=create(client)
    for i in range(2):
        client.post(f"/sessions/{session['session_id']}/turns",headers=auth,json={'turn_id':str(i),'text':'Sannu'})
    response=client.post(f"/sessions/{session['session_id']}/finish",headers=auth)
    assert response.status_code==503
    with main.store.connect() as db:
        assert main.store.session(db,session['session_id'])['status']=='active'

def test_voice_turn_is_linked_to_official_asr_in_export(client, monkeypatch):
    class Provider:
        mode='real'; version='test-n-atlas'
        def ready(self): return True
        def generate(self, *args, **kwargs): return 'Lafiya lau'
    monkeypatch.setattr(main, 'provider', Provider())
    monkeypatch.setattr(main, 'transcribe_audio', lambda audio: 'Sannu' if audio == b'audio' else '')
    response=client.post('/sessions', json={'topic':'greetings','consent':True,'participant_id':'P01'})
    session=response.json(); auth={'Authorization':f"Bearer {session['access_token']}"}
    path=f"/sessions/{session['session_id']}"
    assert client.post(f'{path}/transcriptions/voice-1', content=b'audio', headers={'Content-Type':'audio/mp4'}).status_code==404
    transcription=client.post(f'{path}/transcriptions/voice-1', content=b'audio', headers={**auth,'Content-Type':'audio/mp4'})
    assert transcription.status_code==200
    assert transcription.json()['asr_model']=='NCAIR1/Hausa-ASR'
    assert client.post(f'{path}/turns', json={'turn_id':'voice-1','text':'Changed text'}, headers=auth).status_code==409
    assert client.post(f'{path}/turns', json={'turn_id':'voice-1','text':'Sannu'}, headers=auth).status_code==200
    exported=list(main.store.export())
    assert exported[0]['participant_id']=='P01'
    assert exported[0]['turns'][0]['voice']['asr_model']=='NCAIR1/Hausa-ASR'
    assert exported[0]['turns'][0]['voice']['transcript']=='Sannu'

def test_asr_access_failure_is_clear_and_not_counted(client, monkeypatch):
    class Provider:
        mode='real'; version='test-n-atlas'
        def ready(self): return True
    monkeypatch.setattr(main, 'provider', Provider())
    monkeypatch.setattr(main, 'transcribe_audio', lambda _: (_ for _ in ()).throw(
        RuntimeError('Hugging Face access to NCAIR1/Hausa-ASR is not granted for this account.')))
    session, auth=create(client, consent=True)
    response=client.post(f"/sessions/{session['session_id']}/transcriptions/voice-1",
                         content=b'audio', headers={**auth, 'Content-Type':'audio/mp4'})
    assert response.status_code==503
    assert 'not granted' in response.json()['detail']['message']
    assert list(main.store.export())[0]['turns']==[]
