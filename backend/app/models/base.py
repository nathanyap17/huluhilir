from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.ids import new_ulid

KUCHING_TZ = timezone(timedelta(hours=8))


def now_kuching() -> datetime:
    return datetime.now(KUCHING_TZ)


class KuchingDateTime(TypeDecorator):
    """Every stored timestamp is one clock: Asia/Kuching (UTC+8, CLAUDE.md
    conventions), returned timezone-aware.

    Why this exists (2026-09-24): SQLite has no timezone storage -- it keeps
    the wall-clock digits and silently drops the offset. The phone sends
    correct UTC (`toISOString()` -> "...15:31Z") and the server writes
    now_kuching() ("...23:31+08:00"), so one table held two clocks 8 hours
    apart, and reads came back tz-naive (the root of the earlier
    "can't subtract offset-naive and offset-aware datetimes" 500).

    In:  aware -> converted to Kuching; naive -> taken as Kuching already.
    Out: always aware Kuching. On Postgres (Cloud SQL, timestamptz) the stored
    instant was already right; this only normalises the returned zone.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=KUCHING_TZ)
        return value.astimezone(KUCHING_TZ)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=KUCHING_TZ)
        return value.astimezone(KUCHING_TZ)


class Base(DeclarativeBase):
    pass


def ulid_pk() -> Mapped[str]:
    return mapped_column(primary_key=True, default=new_ulid)
