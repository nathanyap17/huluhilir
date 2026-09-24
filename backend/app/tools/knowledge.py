"""retrieve_knowledge -- L3 hybrid retrieval. docs/PROJECT_SPEC.md §3 L3.

🔄 v2 -- "hybrid: vector similarity + SQLite FTS5 full-text" (§L3's data
table). Now uses real vector embeddings (SentenceTransformers) for the semantic
half, combined with the independent SQLite FTS5 lexical signal
(app/tools/knowledge_fts.py). A doc found by FTS5 gets an additive boost.

Retrieval explains *why*; it never decides *what* (pepperdex-rules skill §1)
-- RetrievalQuery's own default excludes `authoritative` (see
app/schemas/knowledge.py), so this can never surface a dose/product/timing.
"""
import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeDoc
from app.schemas.knowledge import KnowledgeDocOut, RetrievalHit, RetrievalQuery
from app.tools.knowledge_fts import search_fts

_model = None
def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model

# How much an FTS5 lexical match is worth on top of the cosine similarity score
_FTS_BOOST = 0.5

def cosine_similarity(v1, v2):
    dot = np.dot(v1, v2)
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(dot / (norm1 * norm2))

async def retrieve_knowledge(session: AsyncSession, query: RetrievalQuery) -> list[RetrievalHit]:
    stmt = select(KnowledgeDoc).where(KnowledgeDoc.namespace.in_(query.namespaces))
    docs = (await session.execute(stmt)).scalars().all()

    fts_doc_ids = set(await search_fts(session, query.query, top_k=query.top_k * 2))

    model = get_model()
    query_emb = model.encode(query.query)

    scored = []
    for doc in docs:
        fts_hit = doc.doc_id in fts_doc_ids
        
        # If the doc hasn't been embedded yet, fallback to FTS only
        if not doc.embedding:
            if not fts_hit:
                continue
            score = _FTS_BOOST
        else:
            sim = cosine_similarity(query_emb, doc.embedding)
            # Semantic search can return < 0 for opposites, floor at 0 for scoring
            score = max(0.0, sim) + (_FTS_BOOST if fts_hit else 0.0)
            
        scored.append((score, doc))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        RetrievalHit(doc=KnowledgeDocOut.model_validate(doc), score=round(score, 3))
        for score, doc in scored[: query.top_k]
    ]
