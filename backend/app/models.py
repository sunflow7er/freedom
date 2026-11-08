from pydantic import BaseModel
from typing import Any, Optional


class HealthResponse(BaseModel):
    status: str
    time: str


class TranscriptLine(BaseModel):
    timestamp: str
    speaker: str
    text: str


class Conversation(BaseModel):
    id: str
    group_id: str
    channel: str
    language: str
    transcript: list[TranscriptLine]
    audio_url: Optional[str] = None
    imported_at: str


class ChecklistCriterion(BaseModel):
    id: str
    title: str
    type: str                        # "yes_no" | "yes_no_na" | "scale" | "flag"
    weight: int
    na_condition: Optional[str] = None
    scale_steps: Optional[list[int]] = None
    scale_descriptions: Optional[dict[str, str]] = None
    # Free-text rules explaining how to apply this criterion; edited with the
    # criterion itself and inserted into the prompt next to it.
    guidance: Optional[str] = None


class ChecklistConfig(BaseModel):
    # Criterion-agnostic evaluation method, inserted into the prompt before criteria.
    general_rules: list[str] = []
    criteria: list[ChecklistCriterion]


class ChecklistVersionOut(BaseModel):
    id: int
    checklist_id: int
    version: int
    config: Any
    comment: Optional[str]
    created_at: str


class ChecklistOut(BaseModel):
    id: int
    name: str
    channel: str
    active_version_id: Optional[int]
