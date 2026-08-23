"""GET /farms/{farm_id}/dashboard. docs/PROJECT_SPEC.md §7.

huluhilir-rules skill §6 -- **the app must work with zero photographs**. The
rain pulse and the Advisor are computed from weather and farm state alone, so
this endpoint renders usefully on a brand-new farm with no observations, no
diagnosis cycle, and no agent run. Nothing here is gated behind a completed
diagnosis. There is a test for exactly this (tests/test_dashboard.py).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.agent import Alert, Recommendation
from app.models.core import Block, Farm, FlowEdge
from app.schemas.agent import RecommendationOut
from app.schemas.dashboard import DashboardResponse, RainPulse, TerrainNode
from app.schemas.farm import BlockOut, FlowEdgeOut
from app.tools.advisor import should_diagnose
from app.tools.weather import get_weather

router = APIRouter(tags=["dashboard"])

_DAY_NAMES_MS = ["Isnin", "Selasa", "Rabu", "Khamis", "Jumaat", "Sabtu", "Ahad"]


@router.get("/farms/{farm_id}/dashboard", response_model=DashboardResponse)
async def get_dashboard(farm_id: str, session: AsyncSession = Depends(get_session)) -> DashboardResponse:
    farm = await session.get(Farm, farm_id)
    if farm is None:
        raise HTTPException(404, "farm not found")

    blocks = (await session.execute(select(Block).where(Block.farm_id == farm_id))).scalars().all()
    edges = (await session.execute(select(FlowEdge).where(FlowEdge.farm_id == farm_id))).scalars().all()

    weather = get_weather(farm_id)

    # Rain pulse: the next forecast day with meaningful rain. Falls back to the
    # nearest forecast day so the banner always renders something truthful.
    rainy = [f for f in weather.forecast_7d if f.rainfall_mm >= 5.0]
    target = rainy[0] if rainy else (weather.forecast_7d[0] if weather.forecast_7d else None)

    if target is not None:
        from datetime import date
        forecast_date = date.fromisoformat(target.forecast_date)
        days_away = max(0, (forecast_date - date.today()).days)
        rain_pulse = RainPulse(
            day_label=_DAY_NAMES_MS[forecast_date.weekday()],
            rainfall_mm=target.rainfall_mm,
            days_away=days_away,
            speech_template_id="rain_pulse_forecast",
        )
    else:
        rain_pulse = RainPulse(
            day_label="-", rainfall_mm=0.0, days_away=0, speech_template_id="rain_pulse_forecast"
        )

    rain_48h = sum(o.rainfall_mm for o in weather.rainfall_7d[:2])
    rain_since_last = sum(o.rainfall_mm for o in weather.rainfall_7d)
    advisor = await should_diagnose(
        session, farm_id, rain_48h_mm=rain_48h, rain_since_last_cycle_mm=rain_since_last
    )

    # actions[0] only -- the single arbitrated priority action, if any agent
    # run has produced one. Null on a farm that has never run the agent.
    top_action_row = (
        await session.execute(
            select(Recommendation)
            .join(Block, Recommendation.block_id == Block.block_id)
            .where(Block.farm_id == farm_id)
            .order_by(Recommendation.recommended_at.desc(), Recommendation.sequence.asc())
            .limit(1)
        )
    ).scalars().first()

    pending_alerts = len(
        (
            await session.execute(
                select(Alert)
                .join(Block, Alert.target_block_id == Block.block_id)
                .where(Block.farm_id == farm_id, Alert.approved_by_farmer.is_(False))
            )
        ).scalars().all()
    )

    return DashboardResponse(
        farm_id=farm_id,
        rain_pulse=rain_pulse,
        advisor=advisor,
        top_action=RecommendationOut.model_validate(top_action_row) if top_action_row else None,
        terrain_nodes=[
            TerrainNode(
                block_id=b.block_id,
                elevation_rank=b.elevation_rank,
                current_state=b.current_state,
                lat=b.centroid_lat,
                lon=b.centroid_lon,
            )
            for b in sorted(blocks, key=lambda b: b.elevation_rank)
        ],
        terrain_edges=[FlowEdgeOut.model_validate(e) for e in edges],
        pending_neighbour_alerts=pending_alerts,
        blocks=[BlockOut.model_validate(b) for b in blocks],
    )
