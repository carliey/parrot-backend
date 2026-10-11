import json, os, sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

def now(): return datetime.now(timezone.utc).isoformat()
class Store:
    def __init__(self, path=None):
        self.path = path or os.getenv('PARROT_DB', './parrot.sqlite3')
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS sessions (
              id TEXT PRIMARY KEY, token_hash TEXT NOT NULL, topic TEXT NOT NULL, lesson_version TEXT NOT NULL,
              provider_mode TEXT NOT NULL, model_version TEXT NOT NULL, consent INTEGER NOT NULL,
              participant_id TEXT, status TEXT NOT NULL, created_at TEXT NOT NULL, finished_at TEXT, feedback TEXT);
              CREATE TABLE IF NOT EXISTS turns (
              session_id TEXT NOT NULL, turn_id TEXT NOT NULL, learner_text TEXT NOT NULL,
              tutor_text TEXT, processing_ms INTEGER, error TEXT, created_at TEXT NOT NULL,
              PRIMARY KEY(session_id,turn_id));
              CREATE TABLE IF NOT EXISTS transcriptions (
              session_id TEXT NOT NULL, turn_id TEXT NOT NULL, transcript TEXT NOT NULL,
              asr_model TEXT NOT NULL, processing_ms INTEGER NOT NULL, created_at TEXT NOT NULL,
              PRIMARY KEY(session_id,turn_id));
              CREATE TABLE IF NOT EXISTS turn_assessments (
              session_id TEXT NOT NULL, turn_id TEXT NOT NULL, status TEXT NOT NULL,
              skill_evidence TEXT NOT NULL, PRIMARY KEY(session_id,turn_id));''')
    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        finally: db.close()
    def session(self, db, sid):
        return db.execute('SELECT * FROM sessions WHERE id=?', (sid,)).fetchone()
    def turns(self, db, sid):
        rows = db.execute('SELECT * FROM turns WHERE session_id=? ORDER BY created_at,rowid', (sid,)).fetchall()
        assessments = {r['turn_id']: r for r in db.execute(
            'SELECT * FROM turn_assessments WHERE session_id=?', (sid,))}
        result = []
        for row in rows:
            item = dict(row)
            if row['turn_id'] in assessments:
                assessment = assessments[row['turn_id']]
                item['conversation_status'] = assessment['status']
                item['skill_evidence'] = json.loads(assessment['skill_evidence'])
            result.append(item)
        return result
    def export(self):
        with self.connect() as db:
            for row in db.execute("SELECT * FROM sessions WHERE provider_mode='real' AND consent=1 ORDER BY created_at"):
                item = dict(row)
                item.pop('token_hash')
                item['feedback'] = json.loads(item['feedback']) if item['feedback'] else None
                item['turns'] = [dict(t) for t in self.turns(db, row['id'])]
                voice = {r['turn_id']: dict(r) for r in db.execute(
                    'SELECT * FROM transcriptions WHERE session_id=?', (row['id'],))}
                for turn in item['turns']:
                    turn['voice'] = voice.get(turn['turn_id']) if turn['tutor_text'] else None
                yield item
