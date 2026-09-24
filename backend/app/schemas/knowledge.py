"""Knowledge base contracts. docs/DATA_MODEL.md §14.

Rules table decides *what*; retrieval explains *why* — never the reverse.
`local` namespace may never supply dose/product/timing.
"""
from typing import Optional

from pydantic import Field

from app.schemas.common import ORMModel, ulid_field
from app.schemas.enums import KnowledgeNamespace


class KnowledgeDocOut(ORMModel):
    doc_id: str = ulid_field()
    namespace: KnowledgeNamespace
    title: str = Field(max_length=200)
    publisher: Optional[str] = Field(default=None, max_length=80)
    uploaded_by_user_id: Optional[str] = None
    chunk_index: int
    content: str
    citation: str = Field(description="Mandatory")


class RetrievalQuery(ORMModel):
    query: str
    # Retrieval explains *why*; it never decides *what* (pepperdex-rules
    # skill §1) -- authoritative excluded by default so a caller that
    # forgets to override namespaces still can't surface a dose/product/
    # timing. The one real caller (advisor_agent.py) already passes its own
    # ["advisory", "local"] explicitly; this default is the safe fallback
    # for anything written later that doesn't.
    namespaces: list[KnowledgeNamespace] = Field(
        default_factory=lambda: [KnowledgeNamespace.advisory, KnowledgeNamespace.local]
    )
    top_k: int = 5


class RetrievalHit(ORMModel):
    doc: KnowledgeDocOut
    score: float
