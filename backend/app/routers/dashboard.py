"""GET /farms/{farm_id}/dashboard. docs/PROJECT_SPEC.md §7.

pepperdex-rules skill §6 -- **the app must work with zero photographs**. The
rain pulse and the Advisor are computed from weather and farm state alone, so
this endpoint renders usefully on a brand-new farm with no observations, no
diagnosis cycle, and no agent run. Nothing here is gated behind a completed
diagnosis. There is a test for exactly this (tests/test_dashboard.py).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.agent import AgentRun, Alert, Recommendation
from app.models.core import Block, Farm, FlowEdge
from app.models.diagnosis import RiskAssessment
from app.schemas.agent import RecommendationOut
from app.schemas.dashboard import (
    PULSE_THRESHOLD_MM,
    DailyForecast,
    DashboardResponse,
    RainPulseResponse,
    RecommendationDrawer,
    TerrainNode,
)
from app.schemas.farm import BlockOut, FlowEdgeOut
from app.tools.advisor import next_best_check, should_diagnose
from app.tools.terrain import compute_terrain_layout
from app.tools.weather import get_weather

router = APIRouter(tags=["dashboard"])


@router.get("/farms/{farm_id}/dashboard", response_model=DashboardResponse)
async def get_dashboard(farm_id: str, session: AsyncSession = Depends(get_session)) -> DashboardResponse:
    farm = await session.get(Farm, farm_id)
    if farm is None:
        raise HTTPException(404, "farm not found")

    blocks = (await session.execute(select(Block).where(Block.farm_id == farm_id))).scalars().all()
    edges = (await session.execute(select(FlowEdge).where(FlowEdge.farm_id == farm_id))).scalars().all()

    weather = get_weather(farm_id)

    # 🔄 v2 -- all 7 forecast days, not just the next pulse (docs/PROJECT_SPEC.md
    # §9.1, §10 RainPulseResponse). The data already existed in
    # GetWeatherResult.forecast_7d; this used to collapse it to one day.
    rain_pulse = RainPulseResponse(
        forecast_days=[
            DailyForecast(
                date=f.forecast_date,
                rainfall_mm=f.rainfall_mm,
                is_pulse=f.rainfall_mm >= PULSE_THRESHOLD_MM,
                is_cached_fallback=weather.is_cached_fallback,
            )
            for f in weather.forecast_7d
        ],
        station_id=farm.weather_station_id or "Tn187",
        speech_template_id="rain_pulse_forecast",
    )

    rain_48h = sum(o.rainfall_mm for o in weather.rainfall_7d[:2])
    rain_since_last = sum(o.rainfall_mm for o in weather.rainfall_7d)
    advisor = await should_diagnose(
        session, farm_id, rain_48h_mm=rain_48h, rain_since_last_cycle_mm=rain_since_last
    )
    advisor = await next_best_check(
        session, farm_id, advisor, [(f.forecast_date, f.rainfall_mm) for f in weather.forecast_7d]
    )

    # actions[0] only -- the first-sequenced action of the MOST RECENT run that
    # produced any. Previously this sorted every recommendation ever made by
    # recommended_at, so an older run's action scheduled later (or a newer
    # run whose model wrote a stale date) pinned the card to old data and the
    # bento tiles never changed between diagnoses (2026-09-23).
    latest_run_id = (
        await session.execute(
            select(AgentRun.run_id)
            .join(Recommendation, Recommendation.run_id == AgentRun.run_id)
            .where(AgentRun.farm_id == farm_id)
            .order_by(AgentRun.started_at.desc())
            .limit(1)
        )
    ).scalars().first()
    top_action_row = None
    if latest_run_id is not None:
        top_action_row = (
            await session.execute(
                select(Recommendation)
                .where(Recommendation.run_id == latest_run_id)
                .order_by(Recommendation.sequence.asc(), Recommendation.recommended_at.asc())
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

    # §9.2 drawer -- the risk_assessments row for the same run+block as
    # top_action, if compute_spread ever actually ran for it (Phase C:
    # app/agent/runner.py now persists these; older rows predating that
    # change simply have none, so `drawer` stays null rather than guessing).
    drawer = None
    if top_action_row is not None:
        # The block's own projected risk if spread reaches it; otherwise, for
        # the diseased SOURCE block (which compute_spread never lists as its
        # own target), the strongest downhill risk it is projected to cause.
        risk_row = (
            await session.execute(
                select(RiskAssessment).where(
                    RiskAssessment.run_id == top_action_row.run_id,
                    RiskAssessment.block_id == top_action_row.block_id,
                )
            )
        ).scalars().first() or (
            await session.execute(
                select(RiskAssessment)
                .where(
                    RiskAssessment.run_id == top_action_row.run_id,
                    RiskAssessment.source_block_id == top_action_row.block_id,
                )
                .order_by(RiskAssessment.risk_score.desc())
            )
        ).scalars().first()
        if risk_row is not None:
            drawer = RecommendationDrawer(
                risk_score=risk_row.risk_score,
                confidence=risk_row.confidence,
                eta_days=risk_row.eta_days,
                defer_cause=top_action_row.defer_cause,
                rainfall_7d_mm=risk_row.rainfall_7d_mm,
            )

    # §9.6 -- rotated local-metre coordinates for the 3D terrain scene,
    # computed at response time, never persisted (docs/DATA_MODEL.md §5).
    layout = compute_terrain_layout(
        [(b.block_id, b.centroid_lat, b.centroid_lon) for b in blocks],
        [(e.from_block_id, e.to_block_id) for e in edges],
    )

    return DashboardResponse(
        farm_id=farm_id,
        rain_pulse=rain_pulse,
        advisor=advisor,
        top_action=RecommendationOut.model_validate(top_action_row) if top_action_row else None,
        drawer=drawer,
        terrain_nodes=[
            TerrainNode(
                block_id=b.block_id,
                elevation_rank=b.elevation_rank,
                current_state=b.current_state,
                lat=b.centroid_lat,
                lon=b.centroid_lon,
                x_rot_m=layout[b.block_id][0],
                y_rot_m=layout[b.block_id][1],
            )
            for b in sorted(blocks, key=lambda b: b.elevation_rank)
        ],
        terrain_edges=[FlowEdgeOut.model_validate(e) for e in edges],
        pending_neighbour_alerts=pending_alerts,
        blocks=[BlockOut.model_validate(b) for b in blocks],
    )
