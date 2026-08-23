"""`get_treatment` / `find_spray_window` — rules-table lookup + rainfast arithmetic.

huluhilir-rules skill §1: the agent may only output a treatment that exists
in `treatment_options`. This module is the *only* place that table is read;
nothing here calls an LLM, and nothing invents a dose.
"""
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import TreatmentOption
from app.schemas.treatment import (
    FindSprayWindowRequest,
    FindSprayWindowResult,
    GetTreatmentResult,
    SprayWindow,
    TreatmentOptionOut,
)


async def get_treatment(session: AsyncSession, predicted_class: str) -> GetTreatmentResult:
    rows = (await session.execute(select(TreatmentOption))).scalars().all()
    matches = [TreatmentOptionOut.model_validate(r) for r in rows if predicted_class in r.applies_to]
    return GetTreatmentResult(predicted_class=predicted_class, options=matches)


def find_spray_window(req: FindSprayWindowRequest) -> FindSprayWindowResult:
    """A window is viable when no forecast point inside [start, start +
    rainfast_hours] carries meaningful rain. Contact/systemic fungicides wash
    off before absorption if rain falls within the rainfast period
    (docs/PROJECT_SPEC.md §2) -- spraying into that window wastes the product.

    Treatments with no `rainfast_hours` (e.g. biological, cultural) are
    always viable immediately -- there is nothing to wash off.
    """
    if req.rainfast_hours is None:
        now = datetime.now()
        window = SprayWindow(window_start=now, window_end=now + timedelta(hours=1), rain_free=True)
        return FindSprayWindowResult(
            treatment_id=req.treatment_id, rainfast_hours=None,
            viable_windows=[window], recommended_window=window, defer_cause=None,
        )

    RAIN_THRESHOLD_MM = 5.0  # below this, treat the day as effectively dry for rainfast purposes
    windows: list[SprayWindow] = []

    for point in req.forecast:
        start = datetime.fromisoformat(point.date)
        end = start + timedelta(hours=req.rainfast_hours)
        rain_free = not any(
            datetime.fromisoformat(p.date) < end and p.rainfall_mm >= RAIN_THRESHOLD_MM
            for p in req.forecast
            if datetime.fromisoformat(p.date) >= start
        )
        windows.append(SprayWindow(window_start=start, window_end=end, rain_free=rain_free))

    viable = [w for w in windows if w.rain_free]
    defer_cause = None if viable else "rainfast"

    return FindSprayWindowResult(
        treatment_id=req.treatment_id,
        rainfast_hours=req.rainfast_hours,
        viable_windows=windows,
        recommended_window=viable[0] if viable else None,
        defer_cause=defer_cause,
    )
