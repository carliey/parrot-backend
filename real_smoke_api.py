"""Run the real configured model through the FastAPI endpoints. No fake provider."""
import os, subprocess, time
from fastapi.testclient import TestClient
from app.main import app

def memory():
    result=subprocess.run(['memory_pressure','-Q'],capture_output=True,text=True)
    return ' '.join(x.strip() for x in result.stdout.splitlines() if 'free percentage' in x.lower() or 'System-wide free' in x)

print('memory_before:',memory())
with TestClient(app) as client:
    print('ready:',client.get('/ready').json())
    response=client.post('/sessions',json={'topic':'greetings','consent':False})
    if response.status_code!=200: raise SystemExit(f'start failed: {response.status_code} {response.text}')
    session=response.json()
    print('initial_tutor:',session['initial_tutor_message'])
    headers={'Authorization':'Bearer '+session['access_token']}
    for i,message in enumerate(['Sannu! Sunana Amina.','Me na ce maka sunana?'],1):
        start=time.monotonic()
        reply=client.post(f"/sessions/{session['session_id']}/turns",headers=headers,json={'turn_id':f'smoke-{i}','text':message})
        print(f'turn_{i}_status:',reply.status_code,'wall_seconds:',round(time.monotonic()-start,2))
        print(f'turn_{i}_body:',reply.json())
        if reply.status_code!=200: raise SystemExit(1)
    started=time.monotonic()
    finished=client.post(f"/sessions/{session['session_id']}/finish",headers=headers)
    print('finish_status:',finished.status_code,'wall_seconds:',round(time.monotonic()-started,2))
    print('finish_body:',finished.json())
print('memory_after:',memory())
