"""Tests for Google Calendar MCP Server & Guardrailed Autonomous Scheduling (Phase 2 & Phase 3).
"""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent.mcp_calendar_client import get_mcp_calendar_status
from app.db import get_session
from app.main import app
from app.models.base import Base


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        async def _override():
            yield session

        app.dependency_overrides[get_session] = _override
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as http:
            yield http, session
        app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_mcp_calendar_server_status():
    """Verify that Google Calendar MCP server starts via stdio, handshakes, and exposes tools."""
    status = await get_mcp_calendar_status()
    assert status["mcp_connected"] is True
    assert status["server_name"] == "google-calendar"
    expected_tools = [
        "list_upcoming_events",
        "check_availability",
        "create_calendar_event",
        "update_calendar_event",
        "delete_calendar_event",
    ]
    for tool_name in expected_tools:
        assert tool_name in status["tools"], f"Tool {tool_name} should be registered in MCP"


@pytest.mark.asyncio
async def test_mcp_calendar_status_endpoint(client):
    """Test GET /api/calendar/mcp/status endpoint."""
    http, _session = client
    resp = await http.get("/api/calendar/mcp/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["mcp_connected"] is True
    assert "tools" in data
    assert len(data["tools"]) >= 5


@pytest.mark.asyncio
async def test_calendar_proposal_guardrails_lifecycle(client):
    """Verify Rule 13 Human-in-the-Loop guardrail for calendar proposals:
    1. Proposal created with status=pending_approval, approved_by_farmer=False.
    2. Approval endpoint requires explicit farmer_confirmed=True.
    3. Rejection transitions status to rejected.
    """
    http, _session = client
    farm_id = "farm_test_mcp_guardrail"
    proposal_payload = {
        "title": "Rawatan Semburan Kuprum Hidroksida - Blok A",
        "start_iso": "2026-09-25T08:00:00+08:00",
        "end_iso": "2026-09-25T10:00:00+08:00",
        "description": "Semburan racun kulat berjadual pada cuaca kering.",
        "location": "Blok A, Ladang Lada",
    }

    # 1. Create Proposal (Draft)
    create_resp = await http.post(f"/farms/{farm_id}/calendar-proposals", json=proposal_payload)
    assert create_resp.status_code == 201
    created_data = create_resp.json()
    proposal_id = created_data["proposal_id"]
    assert created_data["status"] == "pending_approval"
    assert created_data["approved_by_farmer"] is False

    # 2. List Proposals
    list_resp = await http.get(f"/farms/{farm_id}/calendar-proposals")
    assert list_resp.status_code == 200
    proposals = list_resp.json()
    assert any(p["proposal_id"] == proposal_id for p in proposals)

    # 3. Reject Proposal
    reject_resp = await http.post(f"/api/calendar/proposals/{proposal_id}/reject")
    assert reject_resp.status_code == 200
    assert reject_resp.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_approve_proposal_without_confirmation_fails(client):
    """Guardrail test: Attempting to approve without farmer confirmation returns 400."""
    http, _session = client
    farm_id = "farm_test_guardrail_gate"
    proposal_payload = {
        "title": "Rawatan Siraman - Blok B",
        "start_iso": "2026-09-26T08:00:00+08:00",
        "description": "Siraman fungisida.",
    }
    create_resp = await http.post(f"/farms/{farm_id}/calendar-proposals", json=proposal_payload)
    proposal_id = create_resp.json()["proposal_id"]

    # Call approve with farmer_confirmed=False
    approve_resp = await http.post(
        f"/api/calendar/proposals/{proposal_id}/approve",
        json={"farmer_confirmed": False},
    )
    assert approve_resp.status_code == 400
    assert "farmer confirmation is required" in approve_resp.json()["detail"].lower()
