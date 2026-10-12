import asyncio
import base64
import hashlib
import json
import logging
import secrets
import time
import uuid

from fastapi import FastAPI, Header, HTTPException, Request

from .lessons import (LESSONS, LESSON_VERSION, tutor_prompt, accepts, completed_steps,
                      progress, reply_schema, validated_reply, matching_step)
from .provider import make_provider
from . import general_practice
from . import tts
from .runtime import validate_runtime
from .schemas import Feedback, FinishResponse, HealthResponse, ReadyResponse, LessonsResponse, StartRequest, StartResponse, TurnRequest, TurnResponse, TranscriptionResponse
from .asr import MODEL_ID as ASR_MODEL_ID, transcribe as transcribe_audio
from .store import Store, now

validate_runtime()
provider = make_provider()
store = Store()
locks: dict[str, asyncio.Lock] = {}
capacity = asyncio.Semaphore(1)
waiting = asyncio.Semaphore(2)
app = FastAPI(title='Parrot Hausa Practice API', version='0.1.0')
logger = logging.getLogger('uvicorn.error')
speech_capacity = asyncio.Semaphore(1)


@app.post('/sessions/{session_id}/speech/{message_id}')
async def speech(session_id: str, message_id: str, authorization: str | None = Header(default=None)):
    session = session_for(session_id, authorization)
    if session['topic'] != 'general-practice':
        raise HTTPException(404, detail={'message': 'Audio is available in Putting it together.'})
    with store.connect() as db:
        if message_id == 'opening':
            text = LESSONS[session['topic']]['opening']
        else:
            row = db.execute('SELECT tutor_text FROM turns WHERE session_id=? AND turn_id=?',
                             (session_id, message_id)).fetchone()
            if not row or not row['tutor_text']:
                raise HTTPException(404, detail={'message': 'Tutor reply not found.'})
            text = row['tutor_text']
    voice, model = tts.settings()
    try:
        await asyncio.wait_for(speech_capacity.acquire(), timeout=2)
    except TimeoutError:
        raise HTTPException(429, detail={'message': 'Tutor audio is busy. Tap replay shortly.'})
    try:
        with store.connect() as db:
            row = db.execute('SELECT audio FROM speech_audio WHERE session_id=? AND message_id=? AND voice=? AND model=?',
                             (session_id, message_id, voice, model)).fetchone()
        audio = row['audio'] if row else None
        if audio is None:
            try:
                audio = await asyncio.to_thread(tts.synthesize, text)
            except RuntimeError as exc:
                raise HTTPException(503, detail={'message': str(exc)}) from None
            with store.connect() as db:
                db.execute('INSERT OR REPLACE INTO speech_audio VALUES (?,?,?,?,?)',
                           (session_id, message_id, voice, model, audio))
        return {'audio_base64': base64.b64encode(audio).decode(), 'mime_type': 'audio/mpeg'}
    finally:
        speech_capacity.release()


def session_for(sid: str, authorization: str | None):
    token = (authorization or '').removeprefix('Bearer ').strip()
    with store.connect() as db:
        row = store.session(db, sid)
    if not row or not token or not secrets.compare_digest(row['token_hash'], hashlib.sha256(token.encode()).hexdigest()):
        raise HTTPException(404, detail={'code': 'session_not_found', 'message': 'Session not found or access denied'})
    if row['provider_mode'] != provider.mode:
        raise HTTPException(503, detail={'code': 'provider_changed', 'message': 'Session provider is unavailable'})
    if row['lesson_version'] != LESSON_VERSION:
        raise HTTPException(409, detail={'code': 'lesson_updated', 'message': 'This lesson has been updated. Start a new practice session.'})
    return row


async def generate_bounded(messages, max_tokens, schema=None):
    try:
        await asyncio.wait_for(waiting.acquire(), timeout=0.01)
    except TimeoutError:
        raise HTTPException(429, detail={'code': 'queue_full', 'message': 'Tutor queue is full; retry'})
    try:
        try:
            await asyncio.wait_for(capacity.acquire(), timeout=2)
        except TimeoutError:
            raise HTTPException(429, detail={'code': 'queue_full', 'message': 'Tutor is busy; retry'})
    finally:
        waiting.release()
    try:
        return await asyncio.to_thread(provider.generate, messages, max_tokens, schema)
    finally:
        capacity.release()


@app.get('/health', response_model=HealthResponse)
def health():
    return {'status': 'alive'}


@app.get('/ready', response_model=ReadyResponse)
def ready():
    return {'ready': provider.ready(), 'provider_mode': provider.mode, 'model_version': provider.version}


@app.get('/lessons', response_model=LessonsResponse)
def lessons():
    return {'version': LESSON_VERSION, 'language_review': 'pending', 'lessons': list(LESSONS.values())}


@app.post('/sessions', response_model=StartResponse)
def start(body: StartRequest):
    if not provider.ready():
        raise HTTPException(503, detail={'code': 'provider_unavailable', 'message': 'Model is not loaded'})
    sid, token = str(uuid.uuid4()), secrets.token_urlsafe(32)
    with store.connect() as db:
        db.execute('INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                   (sid, hashlib.sha256(token.encode()).hexdigest(), body.topic, LESSON_VERSION,
                    provider.mode, provider.version, int(body.consent), body.participant_id,
                    'active', now(), None, None))
    return StartResponse(session_id=sid, access_token=token, provider_mode=provider.mode,
                         initial_tutor_message=LESSONS[body.topic]['opening'],
                         lesson_progress=progress(body.topic))


@app.post('/sessions/{session_id}/turns', response_model=TurnResponse)
async def turn(session_id: str, body: TurnRequest, authorization: str | None = Header(default=None)):
    session_for(session_id, authorization)
    lock = locks.setdefault(session_id, asyncio.Lock())
    if lock.locked():
        raise HTTPException(429, detail={'code': 'session_busy', 'message': 'Another turn is processing'})
    async with lock:
        with store.connect() as db:
            session = store.session(db, session_id)
            if session['status'] != 'active':
                raise HTTPException(409, detail={'code': 'session_finished', 'message': 'Session is finished'})
            prior = db.execute('SELECT * FROM turns WHERE session_id=? AND turn_id=?',
                               (session_id, body.turn_id)).fetchone()
            voice = db.execute('SELECT transcript FROM transcriptions WHERE session_id=? AND turn_id=?',
                               (session_id, body.turn_id)).fetchone()
            if voice and voice['transcript'] != body.text:
                raise HTTPException(409, detail={'code': 'transcript_mismatch', 'message': 'This voice turn must use its ASR transcript'})
            rows = store.turns(db, session_id)
            if prior:
                if prior['learner_text'] != body.text:
                    raise HTTPException(409, detail={'code': 'turn_id_conflict', 'message': 'Turn ID was used with different text'})
                if prior['tutor_text']:
                    # A retry returns the original step state even after later turns.
                    prior_index = next(i for i, row in enumerate(rows) if row['turn_id'] == body.turn_id)
                    return TurnResponse(turn_id=body.turn_id, tutor_response=prior['tutor_text'],
                                        processing_ms=prior['processing_ms'], provider_mode=provider.mode,
                                        lesson_progress=progress(session['topic'], rows[:prior_index + 1]))
            state = progress(session['topic'], rows)
            mixed = LESSONS[session['topic']]['mode'] == 'mixed'
            if state['complete'] and not mixed:
                raise HTTPException(409, detail={'code': 'lesson_complete', 'message': 'You have completed the lesson steps. Tap Finish for your practice notes.'})
            if mixed:
                system_prompt = general_practice.tutor_prompt(body.text, rows)
                schema = general_practice.response_schema(body.text, rows)
            else:
                match = matching_step(session['topic'], rows, body.text)
                if match is None:
                    raise HTTPException(422, detail={'code': 'lesson_step_expected',
                        'message': f"{state['instruction']}. You can try “{state['hint']}” ({state['hint_english']}).",
                        'lesson_progress': state})
                step_index, step = match
                system_prompt = tutor_prompt(session['topic'], step_index)
                schema = reply_schema(step)
            messages = [{'role': 'system', 'content': system_prompt},
                        {'role': 'assistant', 'content': LESSONS[session['topic']]['opening']}]
            for row in rows[-6:]:
                if row['tutor_text']:
                    messages += [{'role': 'user', 'content': row['learner_text']},
                                 {'role': 'assistant', 'content': row['tutor_text']}]
            messages.append({'role': 'user', 'content': body.text})
        begun = time.monotonic()
        skill_evidence = []
        conversation_status = None
        try:
            for attempt in range(2):
                raw = await generate_bounded(messages, 400 if mixed else 80, schema)
                try:
                    if mixed:
                        reply, conversation_status, skill_evidence = general_practice.validate_response(raw, body.text, rows)
                    else:
                        reply = validated_reply(raw, step)
                    break
                except (ValueError, TypeError) as validation_error:
                    if attempt:
                        raise
                    messages[0]['content'] += (' Your previous output was invalid. Use the JSON schema, short familiar replies, '
                                              f'and verbatim skill evidence. Fix this issue: {validation_error}.' if mixed else
                                              ' Your previous output was invalid. Follow the exact reply choices and JSON schema.')
                    if mixed:
                        schema = general_practice.repair_schema(body.text, rows)
                        messages.extend([{'role': 'assistant', 'content': raw},
                                         {'role': 'user', 'content': body.text}])
        except HTTPException:
            raise
        except Exception as exc:
            with store.connect() as db:
                db.execute('INSERT OR REPLACE INTO turns VALUES (?,?,?,?,?,?,?)',
                           (session_id, body.turn_id, body.text, None, None, type(exc).__name__, now()))
            raise HTTPException(503, detail={'code': 'inference_failed', 'message': 'Tutor response failed; retry this turn'})
        ms = int((time.monotonic() - begun) * 1000)
        with store.connect() as db:
            db.execute('INSERT OR REPLACE INTO turns VALUES (?,?,?,?,?,?,?)',
                       (session_id, body.turn_id, body.text, reply, ms, None, now()))
            if mixed:
                db.execute('INSERT OR REPLACE INTO turn_assessments VALUES (?,?,?,?)',
                           (session_id, body.turn_id, conversation_status, json.dumps(skill_evidence, ensure_ascii=False)))
            state = progress(session['topic'], store.turns(db, session_id))
        return TurnResponse(turn_id=body.turn_id, tutor_response=reply,
                            processing_ms=ms, provider_mode=provider.mode, lesson_progress=state)


@app.post('/sessions/{session_id}/finish', response_model=FinishResponse)
async def finish(session_id: str, authorization: str | None = Header(default=None)):
    session_for(session_id, authorization)
    lock = locks.setdefault(session_id, asyncio.Lock())
    async with lock:
        with store.connect() as db:
            session = store.session(db, session_id)
            if session['feedback']:
                return FinishResponse(session_id=session_id,
                                      feedback=Feedback.model_validate_json(session['feedback']),
                                      provider_mode=provider.mode)
            turns = [r for r in store.turns(db, session_id) if r['tutor_text']]
        if len(turns) < 2:
            feedback = Feedback(insufficient_evidence=True, tasks_completed=[], expressions_used=[],
                corrections=[], phrases_to_review=LESSONS[session['topic']]['phrases'][:2],
                message='Not enough conversation for detailed feedback yet.')
        else:
            transcript = '\n'.join(f"Learner: {r['learner_text']}\nTutor: {r['tutor_text']}" for r in turns)
            prompt = [
                {'role': 'system', 'content': 'Return concise JSON feedback. At most 2 items per list and at most 1 correction. Keep each explanation under 12 words. Use only exact lesson task strings. Expressions and correction originals must be verbatim learner text. Accept understood ASR spelling variants and toh fillers; never correct these. If no actual error, corrections must be empty. No scores or pronunciation claims.'},
                {'role': 'user', 'content': f"Lesson tasks: {LESSONS[session['topic']]['tasks']}\nTranscript:\n{transcript}"},
            ]
            feedback = None
            for _ in range(2):
                try:
                    raw = await generate_bounded(prompt, 600, Feedback.model_json_schema())
                    feedback = Feedback.model_validate_json(raw)
                    break
                except HTTPException:
                    raise
                except Exception:
                    continue
            if feedback is None:
                raise HTTPException(503, detail={'code': 'feedback_invalid', 'message': 'Could not validate feedback; retry finish'})
            learner_text = '\n'.join(r['learner_text'] for r in turns).casefold()
            allowed_tasks = [step['task'] for step in completed_steps(session['topic'], turns)]
            allowed_phrases = set(LESSONS[session['topic']]['phrases'])
            understood_evidence = [item['evidence'].casefold() for row in turns
                                   for item in row.get('skill_evidence', [])]
            feedback = Feedback(
                insufficient_evidence=False,
                tasks_completed=allowed_tasks,
                expressions_used=[e for e in feedback.expressions_used if e and e.casefold() in learner_text][:2],
                corrections=[c for c in feedback.corrections if c.original and c.original.casefold() in learner_text
                             and c.original.casefold() != c.suggested.casefold() and c.suggested in allowed_phrases
                             and c.original.casefold() not in understood_evidence
                             and not any(accepts(step, c.original) for step in LESSONS[session['topic']]['steps'])][:1],
                phrases_to_review=[p for p in feedback.phrases_to_review if p in allowed_phrases][:2],
                message='Feedback based on this text conversation. No pronunciation assessment was made.',
            )
        with store.connect() as db:
            db.execute("UPDATE sessions SET status='finished', finished_at=?, feedback=? WHERE id=?",
                       (now(), feedback.model_dump_json(), session_id))
        return FinishResponse(session_id=session_id, feedback=feedback, provider_mode=provider.mode)


@app.post('/sessions/{session_id}/transcriptions/{turn_id}', response_model=TranscriptionResponse)
async def transcribe(session_id: str, turn_id: str, request: Request,
                     authorization: str | None = Header(default=None)):
    session = session_for(session_id, authorization)
    if session['status'] != 'active':
        raise HTTPException(409, detail={'code': 'session_finished', 'message': 'Session is finished'})
    if not (1 <= len(turn_id) <= 80 and all(c.isalnum() or c in '_-' for c in turn_id)):
        raise HTTPException(422, detail={'code': 'invalid_turn_id', 'message': 'Invalid turn ID'})
    # Expo's native File upload may use application/octet-stream or omit the
    # media type. Decode the bounded bytes with ffmpeg instead of trusting it.
    with store.connect() as db:
        prior = db.execute('SELECT * FROM transcriptions WHERE session_id=? AND turn_id=?',
                           (session_id, turn_id)).fetchone()
    if prior:
        return TranscriptionResponse(turn_id=turn_id, transcript=prior['transcript'],
                                     asr_model=prior['asr_model'], processing_ms=prior['processing_ms'])
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > 5_000_000:
            raise HTTPException(413, detail={'code': 'audio_too_large', 'message': 'Recording exceeds 5 MB'})
        chunks.append(chunk)
    if size == 0:
        logger.warning('Transcription rejected: empty_audio (0 uploaded bytes)')
        raise HTTPException(422, detail={'code': 'empty_audio', 'message': 'Recording is empty'})
    begun = time.monotonic()
    try:
        transcript = await asyncio.to_thread(transcribe_audio, b''.join(chunks))
    except ValueError as exc:
        logger.warning('Transcription rejected: invalid_audio (%d uploaded bytes): %s', size, exc)
        raise HTTPException(422, detail={'code': 'invalid_audio', 'message': str(exc)}) from exc
    except RuntimeError as exc:
        # ASR RuntimeErrors contain safe messages, never remote exception details.
        logger.warning('Transcription unavailable: %s', exc)
        raise HTTPException(503, detail={'code': 'asr_unavailable', 'message': str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(503, detail={'code': 'asr_unavailable', 'message': f'Hausa ASR failed: {type(exc).__name__}'}) from exc
    if not transcript or len(transcript) > 500:
        logger.warning('Transcription rejected: no_speech (%d uploaded bytes, %d transcript characters)',
                       size, len(transcript or ''))
        raise HTTPException(422, detail={'code': 'no_speech', 'message': 'No usable Hausa speech was detected; try again'})
    ms = int((time.monotonic() - begun) * 1000)
    with store.connect() as db:
        db.execute('INSERT OR IGNORE INTO transcriptions VALUES (?,?,?,?,?,?)',
                   (session_id, turn_id, transcript, ASR_MODEL_ID, ms, now()))
    return TranscriptionResponse(turn_id=turn_id, transcript=transcript,
                                 asr_model=ASR_MODEL_ID, processing_ms=ms)


@app.post('/speech/synthesize')
def synthesis_unavailable():
    raise HTTPException(501, detail={'code': 'speech_unavailable', 'message': 'Hausa TTS is not configured'})
