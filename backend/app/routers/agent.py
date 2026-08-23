from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.runner import run_root_agent
from app.db import get_session
from app.schemas.advisor import AdvisorVerdictOut
from app.schemas.agent import AgentRunOut
from app.tools.advisor import should_diagnose
from app.tools.weather import get_weather

router = APIRouter(tags=["agent"])


class AgentRunRequest(BaseModel):
    farm_id: str
    message: str
    cycle_id: Optional[str] = None
    trigger: str = "manual"


@router.post("/agent/run", response_model=AgentRunOut)
async def agent_run(req: AgentRunRequest, session: AsyncSession = Depends(get_session)) -> AgentRunOut:
    agent_run_row = await run_root_agent(
        session, req.farm_id, req.message, cycle_id=req.cycle_id, trigger=req.trigger
    )
    await session.commit()
    return AgentRunOut.model_validate(agent_run_row)


@router.get("/farm/{farm_id}/advisor", response_model=AdvisorVerdictOut)
async def get_advisor(farm_id: str, session: AsyncSession = Depends(get_session)) -> AdvisorVerdictOut:
    """Computed at request time -- no background polling (huluhilir-rules skill §6)."""
    weather = get_weather(farm_id)
    rain_48h = sum(o.rainfall_mm for o in weather.rainfall_7d[:2])
    rain_since_last = sum(o.rainfall_mm for o in weather.rainfall_7d)
    return await should_diagnose(session, farm_id, rain_48h_mm=rain_48h, rain_since_last_cycle_mm=rain_since_last)
