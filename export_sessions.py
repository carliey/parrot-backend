import json
from app.store import Store
for session in Store().export():
    print(json.dumps(session, ensure_ascii=False))
