"""Exposes the five deterministic tools over HTTP so they're callable via
/docs with valid Pydantic responses (PLAN.md Block B exit criteria). The ADK
agent in Block C wraps these same functions as FunctionTools directly --
this router exists for manual testing and for any client that wants raw
tool access without going through the agent.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.diagnosis import DiagnoseLeafRequest, DiagnoseLeafResult
from app.schemas.spread import ComputeSpreadRequest, ComputeSpreadResult
from app.schemas.treatment import (
    FindSprayWindowRequest,
    FindSprayWindowResult,
    GetTreatmentRequest,
    GetTreatmentResult,
)
from app.schemas.weather import GetWeatherRequest, GetWeatherResult
from app.tools.diagnose import diagnose_leaf as diagnose_leaf_tool
from app.tools.spread import compute_spread as compute_spread_tool
from app.tools.treatment import find_spray_window as find_spray_window_tool
from app.tools.treatment import get_treatment as get_treatment_tool
from app.tools.weather import get_weather as get_weather_tool

router = APIRouter(prefix="/tools", tags=["tools"])


@router.post("/compute_spread", response_model=ComputeSpreadResult)
async def compute_spread(req: ComputeSpreadRequest) -> ComputeSpreadResult:
    return compute_spread_tool(req)


@router.post("/get_weather", response_model=GetWeatherResult)
async def get_weather(req: GetWeatherRequest) -> GetWeatherResult:
    return get_weather_tool(req.farm_id)


@router.post("/get_treatment", response_model=GetTreatmentResult)
async def get_treatment(req: GetTreatmentRequest, session: AsyncSession = Depends(get_session)) -> GetTreatmentResult:
    return await get_treatment_tool(session, req.predicted_class)


@router.post("/find_spray_window", response_model=FindSprayWindowResult)
async def find_spray_window(req: FindSprayWindowRequest) -> FindSprayWindowResult:
    return find_spray_window_tool(req)


@router.post("/diagnose_leaf", response_model=DiagnoseLeafResult)
async def diagnose_leaf(req: DiagnoseLeafRequest) -> DiagnoseLeafResult:
    return diagnose_leaf_tool(req.observation_id, req.image_uri, req.capture_target)
