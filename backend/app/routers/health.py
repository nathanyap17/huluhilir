"""Health and service-discovery endpoints.

`GET /` exists because the deployed Cloud Run URL is a link people actually
open in a browser (judges, teammates) -- FastAPI's default for an
undeclared root is `{"detail":"Not Found"}`, which reads as "the deploy is
broken" even when every real route is healthy. This returns something
self-describing instead and points at /docs.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.models.core import Block, Farm
from app.models.knowledge import TreatmentOption

router = APIRouter(tags=["health"])


@router.get("/")
async def root() -> dict:
    return {
        "service": "huluhilir-api",
        "description": (
            "Terrain-aware agentic early warning for Phytophthora foot rot "
            "in Sarawak black pepper. AICC 2026 - Track 3, Category B."
        ),
        "docs": "/docs",
        "health": "/health",
        "farms": "/farms",
        "llm_model": settings.litellm_model,
    }


@router.get("/health")
async def health() -> dict:
    return {"ok": True, "service": "huluhilir-api"}


@router.get("/health/ready")
async def ready(session: AsyncSession = Depends(get_session)) -> dict:
    """Liveness is not enough to trust a CLOUD deploy.

    Cloud Run's filesystem is ephemeral, so `/health` returning ok only
    proves the process booted -- it says nothing about whether the seed
    actually ran on this instance. This counts the rows the app cannot
    function without, so a half-initialised instance is visible rather
    than silently serving empty dashboards. See docs/BUILD_LOG.md
    "Cloud deploy".
    """
    treatments = await session.scalar(select(func.count()).select_from(TreatmentOption))
    farms = await session.scalar(select(func.count()).select_from(Farm))
    blocks = await session.scalar(select(func.count()).select_from(Block))
    return {
        "ok": bool(treatments) and bool(farms),
        "seeded": {"treatment_rules": treatments, "farms": farms, "blocks": blocks},
        "database_url_scheme": settings.database_url.split("://", 1)[0],
    }
