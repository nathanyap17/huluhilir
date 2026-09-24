from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models import Base

engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    """create_all(); Alembic is skipped for the 24h build (PLAN.md Block A)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # 🔄 v2 -- knowledge_docs_fts (docs/DATA_MODEL.md §14a): SQLite-only,
        # not a SQLAlchemy model since FTS5 virtual tables aren't ORM-mapped
        # tables. Guarded by dialect: Postgres (Cloud SQL, if ever migrated)
        # has no FTS5 -- this is a search index, not a source of truth, so
        # skipping it there costs nothing but hybrid search's lexical half.
        if settings.database_url.startswith("sqlite"):
            await conn.execute(text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_docs_fts "
                "USING fts5(doc_id UNINDEXED, content)"
            ))


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
