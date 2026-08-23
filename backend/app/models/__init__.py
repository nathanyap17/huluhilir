"""Import every model module so Base.metadata.create_all() sees the full schema."""
from app.models.base import Base
from app.models import agent, core, diagnosis, knowledge, speech, weather  # noqa: F401

__all__ = ["Base"]
