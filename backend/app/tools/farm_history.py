"""query_farm_history -- structured data tool. docs/PROJECT_SPEC.md §3 L3.

"Historical diagnoses / risk assessments / recommendations -> New tool
query_farm_history(farm_id, filters) -- direct SQL, never embedded as text."
Structured data loses its structure the moment it's flattened for embedding
-- a tool call over real rows is more reliable than hoping semantic search
retrieves the right number. This is why it lives beside retrieve_knowledge
but never touches knowledge_docs or the FTS index at all.
"""
from datetime import timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Recommendation
from app.models.core import Block
from app.models.diagnosis import Diagnosis, Observation, RiskAssessment
from app.models.base import now_kuching


async def query_farm_history(
    session: AsyncSession,
    farm_id: str,
    block_id: Optional[str] = None,
    disease_class: Optional[str] = None,
    since_days: Optional[int] = None,
    limit: int = 20,
) -> dict:
    """Returns real rows from diagnoses, risk_assessments, and
    recommendations for this farm -- filtered, never summarised or
    paraphrased. All filters are optional and combine with AND.
    `since_days` restricts to rows from the last N days.
    """
    cutoff = now_kuching() - timedelta(days=since_days) if since_days is not None else None

    diag_stmt = (
        select(Diagnosis, Observation)
        .join(Observation, Diagnosis.observation_id == Observation.observation_id)
        .join(Block, Observation.block_id == Block.block_id)
        .where(Block.farm_id == farm_id)
        .order_by(Observation.captured_at.desc())
        .limit(limit)
    )
    if block_id is not None:
        diag_stmt = diag_stmt.where(Observation.block_id == block_id)
    if disease_class is not None:
        diag_stmt = diag_stmt.where(Diagnosis.predicted_class == disease_class)
    if cutoff is not None:
        diag_stmt = diag_stmt.where(Observation.captured_at >= cutoff)
    diagnoses = (await session.execute(diag_stmt)).all()

    risk_stmt = (
        select(RiskAssessment)
        .join(Block, RiskAssessment.block_id == Block.block_id)
        .where(Block.farm_id == farm_id)
        .order_by(RiskAssessment.computed_at.desc())
        .limit(limit)
    )
    if block_id is not None:
        risk_stmt = risk_stmt.where(RiskAssessment.block_id == block_id)
    if cutoff is not None:
        risk_stmt = risk_stmt.where(RiskAssessment.computed_at >= cutoff)
    risk_rows = (await session.execute(risk_stmt)).scalars().all()

    rec_stmt = (
        select(Recommendation)
        .join(Block, Recommendation.block_id == Block.block_id)
        .where(Block.farm_id == farm_id)
        .order_by(Recommendation.recommended_at.desc())
        .limit(limit)
    )
    if block_id is not None:
        rec_stmt = rec_stmt.where(Recommendation.block_id == block_id)
    if cutoff is not None:
        rec_stmt = rec_stmt.where(Recommendation.recommended_at >= cutoff)
    recommendations = (await session.execute(rec_stmt)).scalars().all()

    return {
        "diagnoses": [
            {
                "block_id": obs.block_id,
                "predicted_class": diag.predicted_class,
                "confidence": diag.confidence,
                "captured_at": obs.captured_at.isoformat(),
            }
            for diag, obs in diagnoses
        ],
        "risk_assessments": [
            {
                "block_id": r.block_id,
                "risk_score": r.risk_score,
                "risk_band": r.risk_band,
                "eta_days": r.eta_days,
                "is_estimate": r.is_estimate,
                "computed_at": r.computed_at.isoformat(),
            }
            for r in risk_rows
        ],
        "recommendations": [
            {
                "block_id": r.block_id,
                "action_type": r.action_type,
                "treatment_id": r.treatment_id,
                "defer_cause": r.defer_cause,
                "recommended_at": r.recommended_at.isoformat(),
            }
            for r in recommendations
        ],
    }
