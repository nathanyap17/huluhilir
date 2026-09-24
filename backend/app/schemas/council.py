"""Overrun Council contracts. docs/PROJECT_SPEC.md §3 L4, §10, DATA_MODEL.md §24.

Rule 12 / pepperdex-rules skill §12: the council may re-rank already-approved
actions; it may never generate a treatment, dose, or timing. Enforced here
structurally -- `TriageRanking` has no field that could hold one, and
`extra="forbid"` makes that a real wall rather than documentation: pydantic
v2's default behaviour is to silently DROP unknown fields, which would let a
hallucinated `treatment_id` pass validation unnoticed. `forbid` raises
instead (verified in sandbox/exp15_council_wall.py before this was wired
into the real agent).
"""
from datetime import datetime

from pydantic import ConfigDict, Field

from app.schemas.common import ORMModel, ulid_field


class TriageRanking(ORMModel):
    model_config = ConfigDict(extra="forbid")

    block_id: str
    rank: int = Field(ge=1)
    rationale_ms: str = Field(max_length=300)
    # No treatment_id, dose_text, or recommended_at field exists here --
    # enforced by the schema, not by convention (see module docstring).


class CouncilDebateOut(ORMModel):
    debate_id: str = ulid_field()
    run_id: str
    block_ids_considered: list[str]
    transcript: list[dict]
    ranked_output: list[dict]
    created_at: datetime
