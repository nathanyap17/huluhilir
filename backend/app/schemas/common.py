"""Shared base classes and conventions for every schema in this package."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.ids import new_ulid


class ORMModel(BaseModel):
    """Base for schemas that read from SQLAlchemy ORM instances."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


def ulid_field() -> str:
    return Field(default_factory=new_ulid)


def utcnow_kuching() -> datetime:
    """Timestamps are Asia/Kuching (UTC+8) per docs/DATA_MODEL.md convention."""
    from datetime import timedelta, timezone

    return datetime.now(timezone(timedelta(hours=8)))
