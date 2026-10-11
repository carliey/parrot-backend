from typing import Literal
from pydantic import BaseModel, Field

class LessonProgress(BaseModel):
    completed_steps: int
    total_steps: int
    complete: bool
    instruction: str
    hint: str
    hint_english: str

class StartRequest(BaseModel):
    topic: Literal['greetings', 'introductions', 'buying-things', 'general-practice']
    consent: bool = False
    participant_id: str | None = Field(default=None, max_length=80)
class StartResponse(BaseModel):
    session_id: str
    access_token: str
    provider_mode: Literal['real']
    initial_tutor_message: str
    lesson_progress: LessonProgress
class TurnRequest(BaseModel):
    turn_id: str = Field(min_length=1, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')
    text: str = Field(min_length=1, max_length=500)
class TurnResponse(BaseModel):
    turn_id: str
    tutor_response: str
    processing_ms: int
    provider_mode: Literal['real']
    lesson_progress: LessonProgress
class TranscriptionResponse(BaseModel):
    turn_id: str
    transcript: str
    asr_model: str
    processing_ms: int
class Correction(BaseModel):
    original: str
    suggested: str
    explanation: str
class Feedback(BaseModel):
    insufficient_evidence: bool
    tasks_completed: list[str]
    expressions_used: list[str]
    corrections: list[Correction]
    phrases_to_review: list[str]
    message: str
class FinishResponse(BaseModel):
    session_id: str
    feedback: Feedback
    provider_mode: Literal['real']

class HealthResponse(BaseModel):
    status: Literal['alive']
class ReadyResponse(BaseModel):
    ready: bool
    provider_mode: Literal['real']
    model_version: str
class LessonMetadata(BaseModel):
    id: Literal['greetings','introductions','buying-things','general-practice']
    mode: Literal['guided', 'mixed']
    title: str
    description: str
    scenario: str
    tasks: list[str]
    phrases: list[str]
    opening: str
    cultural_notes: list[str]
    vocabulary: list[dict]
class LessonsResponse(BaseModel):
    version: str
    language_review: Literal['pending']
    lessons: list[LessonMetadata]
