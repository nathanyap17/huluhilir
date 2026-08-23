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
    namespaces: list[KnowledgeNamespace] = Field(
        default_factory=lambda: [KnowledgeNamespace.authoritative, KnowledgeNamespace.advisory]
    )
    top_k: int = 5


class RetrievalHit(ORMModel):
    doc: KnowledgeDocOut
    score: float
