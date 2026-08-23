"""Speech template / slot contracts. docs/DATA_MODEL.md §19-21.

Every user-facing string carries a `speech_template_id` — literacy is not
assumed (docs/CLAUDE.md § Non-negotiable rules #7).
"""
from datetime import datetime
from typing import Optional

from pydantic import Field

from app.schemas.common import ORMModel
from app.schemas.enums import Language


class SpeechTemplateOut(ORMModel):
    template_id: str = Field(max_length=30)
    language: Language
    category: str = Field(max_length=30)
    text_template: str = Field(max_length=300)
    slots: list[str] = Field(default_factory=list)
    audio_clip_uri: Optional[str] = Field(default=None, description="MVP: bundled pre-recorded .wav")
    translated_by: Optional[str] = Field(default=None, description="Native-speaker provenance")
    verified: bool = False


class SlotVocabularyOut(ORMModel):
    slot_id: str = Field(max_length=40)
    slot_type: str
    text_ms: str
    text_iba: Optional[str] = None
    verified: bool = False


class RenderSpeechRequest(ORMModel):
    template_id: str
    language: Language
    slots: dict[str, str] = Field(default_factory=dict)
    seed: int = 42


class RenderSpeechResult(ORMModel):
    template_id: str
    language: Language
    rendered_text: str
    audio_uri: str
    duration_ms: Optional[int] = None
    cache_hit: bool = False


class AudioCacheOut(ORMModel):
    hash: str = Field(max_length=64, description="sha256(template_id + slots + lang + seed)")
    template_id: str
    language: Language
    slots_json: dict[str, str]
    audio_path: str
    duration_ms: int
    seed: int
    generated_at: datetime
