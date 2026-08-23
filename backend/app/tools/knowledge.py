"""retrieve_knowledge -- L3 MVP retrieval. docs/PROJECT_SPEC.md §3 L3:
"JSON file + in-memory similarity over ~40 chunks. No vector database."

Keyword-overlap scoring, not embeddings -- the corpus is a handful of chunks
today (see backend/seed/knowledge_docs.json), so this is proportionate; swap
for real embeddings only if the corpus grows enough that overlap scoring
stops separating results meaningfully.

Retrieval explains *why*; it never decides *what* (huluhilir-rules skill §1)
-- this queries `namespace != 'authoritative'` only, so it can never surface
a dose/product/timing.
"""
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeDoc
from app.schemas.knowledge import KnowledgeDocOut, RetrievalHit, RetrievalQuery

_WORD_RE = re.compile(r"[a-zA-Z]+")


def _tokenize(text: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(text)}


async def retrieve_knowledge(session: AsyncSession, query: RetrievalQuery) -> list[RetrievalHit]:
    stmt = select(KnowledgeDoc).where(KnowledgeDoc.namespace.in_(query.namespaces))
    docs = (await session.execute(stmt)).scalars().all()

    query_tokens = _tokenize(query.query)
    scored = []
    for doc in docs:
        doc_tokens = _tokenize(doc.content) | _tokenize(doc.title)
        overlap = len(query_tokens & doc_tokens)
        if overlap == 0:
            continue
        score = overlap / max(1, len(query_tokens))
        scored.append((score, doc))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        RetrievalHit(doc=KnowledgeDocOut.model_validate(doc), score=round(score, 3))
        for score, doc in scored[: query.top_k]
    ]
