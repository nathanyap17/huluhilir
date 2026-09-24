"""SQLite FTS5 lexical half of hybrid search. docs/PROJECT_SPEC.md §3 L3,
docs/DATA_MODEL.md §14a.

`knowledge_docs_fts` is a search index only, never a second source of truth
-- `knowledge_docs` remains authoritative for content. This module owns
keeping the index in sync and querying it; app/tools/knowledge.py combines
its results with the existing keyword-overlap scoring to make retrieval
genuinely hybrid rather than either signal alone.

Not a SQLAlchemy model: FTS5 virtual tables aren't ORM-mapped, so this uses
raw SQL via the session's underlying connection throughout.
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def rebuild_fts_index(session: AsyncSession) -> int:
    """Full rebuild from knowledge_docs -- proportionate at this corpus size
    (~40 chunks, docs/PROJECT_SPEC.md §3 L3) and simpler than wiring
    insert/update/delete triggers for a table nothing currently writes to
    outside seeding (no upload endpoint exists yet for namespace='local').
    Called once after seed_knowledge(); safe to call again any time the
    corpus changes.
    """
    from app.models.knowledge import KnowledgeDoc
    from sqlalchemy import select

    await session.execute(text("DELETE FROM knowledge_docs_fts"))
    docs = (await session.execute(select(KnowledgeDoc))).scalars().all()
    for doc in docs:
        await session.execute(
            text("INSERT INTO knowledge_docs_fts (doc_id, content) VALUES (:doc_id, :content)"),
            {"doc_id": doc.doc_id, "content": f"{doc.title}\n{doc.content}"},
        )
    return len(docs)


async def search_fts(session: AsyncSession, query: str, top_k: int) -> list[str]:
    """Returns doc_ids ranked by FTS5's bm25 relevance (ascending `rank` is
    FTS5's documented best-match-first order). A query with no valid FTS5
    tokens (e.g. pure punctuation) or a malformed MATCH expression fails
    closed to an empty list rather than raising -- retrieval must degrade
    gracefully, never break the Advisor's answer path."""
    # FTS5 query syntax treats a bare multi-word string as an implicit AND
    # of terms; a farmer's free-form question may contain characters MATCH
    # treats as operators (", *, ^, -), so quote each token individually
    # rather than passing the raw question straight through.
    tokens = [t for t in query.replace('"', " ").split() if t]
    if not tokens:
        return []
    match_expr = " OR ".join(f'"{t}"' for t in tokens)

    try:
        rows = await session.execute(
            text(
                "SELECT doc_id FROM knowledge_docs_fts "
                "WHERE knowledge_docs_fts MATCH :match_expr "
                "ORDER BY rank LIMIT :top_k"
            ),
            {"match_expr": match_expr, "top_k": top_k},
        )
        return [r[0] for r in rows.all()]
    except Exception:
        return []
