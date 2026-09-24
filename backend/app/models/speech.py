"""speech_templates, slot_vocabulary, audio_cache. docs/DATA_MODEL.md §19-21."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import KuchingDateTime, Base, now_kuching


class SpeechTemplate(Base):
    __tablename__ = "speech_templates"

    template_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    language: Mapped[str] = mapped_column(String(4))
    category: Mapped[str] = mapped_column(String(30))
    text_template: Mapped[str] = mapped_column(String(300))
    slots: Mapped[list] = mapped_column(JSON, default=list)
    audio_clip_uri: Mapped[str | None] = mapped_column(String(255))
    translated_by: Mapped[str | None] = mapped_column(String(80))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)


class SlotVocabulary(Base):
    __tablename__ = "slot_vocabulary"

    slot_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    slot_type: Mapped[str] = mapped_column(String(20))
    text_ms: Mapped[str] = mapped_column(String(60))
    text_iba: Mapped[str | None] = mapped_column(String(60))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)


class AudioCache(Base):
    """Optimised tier only. Synthesis costs 1-3s; cached playback is instant."""

    __tablename__ = "audio_cache"

    hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    template_id: Mapped[str] = mapped_column(String(30))
    language: Mapped[str] = mapped_column(String(4))
    slots_json: Mapped[dict] = mapped_column(JSON)
    audio_path: Mapped[str] = mapped_column(String(255))
    duration_ms: Mapped[int] = mapped_column(Integer)
    seed: Mapped[int] = mapped_column(Integer)
    generated_at: Mapped[datetime] = mapped_column(KuchingDateTime(), default=now_kuching)
