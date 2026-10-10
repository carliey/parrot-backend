"""Count consenting, successful real voice exchanges for NAIC validation."""

import json
from collections import Counter

from app.store import Store

sessions = list(Store().export())
voice_turns = [turn for session in sessions for turn in session['turns']
               if turn['tutor_text'] and turn['voice']
               and turn['voice']['transcript'] == turn['learner_text']]
participants = {s['participant_id'] for s in sessions if s['participant_id']
                and any(t['tutor_text'] and t['voice'] for t in s['turns'])}
summary = {
    'consenting_real_sessions': len(sessions),
    'completed_voice_interactions': len(voice_turns),
    'participants_with_codes': len(participants),
    'asr_models': dict(Counter(t['voice']['asr_model'] for t in voice_turns)),
    'llm_models': dict(Counter(s['model_version'] for s in sessions)),
    'counting_rule': 'One successful official-ASR transcript followed by a real N-ATLaS reply; retries count once.',
}
print(json.dumps(summary, ensure_ascii=False, indent=2))
