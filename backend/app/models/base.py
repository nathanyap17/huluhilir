from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.ids import new_ulid

KUCHING_TZ = timezone(timedelta(hours=8))


def now_kuching() -> datetime:
    return datetime.now(KUCHING_TZ)


class Base(DeclarativeBase):
    pass


def ulid_pk() -> Mapped[str]:
    return mapped_column(primary_key=True, default=new_ulid)
