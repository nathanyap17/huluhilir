"""treatment_options, treatment_applications, knowledge_docs. docs/DATA_MODEL.md §12-14."""
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import KuchingDateTime, Base, now_kuching


class TreatmentOption(Base):
    """Namespace A, seeded. Hard rule: the agent may never output a treatment absent from this table."""

    __tablename__ = "treatment_options"

    treatment_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    name_ms: Mapped[str] = mapped_column(String(80))
    name_en: Mapped[str] = mapped_column(String(80))
    type: Mapped[str] = mapped_column(String(12))
    applies_to: Mapped[list] = mapped_column(JSON)
    rainfast_hours: Mapped[Optional[int]] = mapped_column(Integer)
    dose_text_ms: Mapped[Optional[str]] = mapped_column(String(200))
    application_method: Mapped[str] = mapped_column(String(20))
    reentry_hours: Mapped[Optional[int]] = mapped_column(Integer)
    source_ref: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[Optional[str]] = mapped_column(String(255))


class TreatmentApplication(Base):
    __tablename__ = "treatment_applications"

    application_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    block_id: Mapped[str] = mapped_column(ForeignKey("blocks.block_id"))
    treatment_id: Mapped[str] = mapped_column(ForeignKey("treatment_options.treatment_id"))
    applied_at: Mapped[datetime] = mapped_column(KuchingDateTime())
    followed_recommendation: Mapped[Optional[bool]] = mapped_column(Boolean)
    recommendation_id: Mapped[Optional[str]] = mapped_column(String(26))
    rain_within_rainfast: Mapped[Optional[bool]] = mapped_column(Boolean)
    rainfall_after_mm: Mapped[Optional[float]] = mapped_column(Float)


class KnowledgeDoc(Base):
    """`local` namespace may never supply dose/product/timing."""

    __tablename__ = "knowledge_docs"

    doc_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    namespace: Mapped[str] = mapped_column(String(15))
    title: Mapped[str] = mapped_column(String(200))
    publisher: Mapped[Optional[str]] = mapped_column(String(80))
    uploaded_by_user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.user_id"))
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[Optional[list]] = mapped_column(JSON)
    citation: Mapped[str] = mapped_column(String(255))
