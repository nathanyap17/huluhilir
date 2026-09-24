"""One Google token per backend -> one owning farm (2026-09-24). Any phone
that installs the APK must not be able to take over, read, or write the
team's Google Calendar; and the shared demo farm must never own it."""
from datetime import datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent import mcp_calendar_client
from app.db import get_session
from app.main import app
from app.models.agent import CalendarEventProposal
from app.models.base import Base
from app.tools import calendar_service


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(calendar_service, "OWNER_FILE", tmp_path / "calendar_owner.json")
    monkeypatch.delenv("CALENDAR_OWNER_FARM_ID", raising=False)
    monkeypatch.setattr(calendar_service, "is_calendar_connected", lambda: True)
    monkeypatch.setattr(calendar_service, "get_authorization_url",
                        lambda redirect_uri=None, state=None: ("https://accounts.google.com/x", state))
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        async def _override():
            yield session

        app.dependency_overrides[get_session] = _override
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as http:
            yield http, session, monkeypatch
        app.dependency_overrides.clear()
    await engine.dispose()


async def _farm(http, name="F"):
    user = (await http.post("/users", json={"display_name": "N", "district": "Sibu"})).json()
    return (await http.post("/farms", json={"user_id": user["user_id"], "name": name,
                                            "centroid_lat": 2.3, "centroid_lon": 111.8})).json()["farm_id"]


async def _proposal(session, farm_id):
    p = CalendarEventProposal(farm_id=farm_id, title="Rawatan", start_time=datetime(2026, 9, 29, 8),
                              end_time=datetime(2026, 9, 29, 9), description="d", location="l",
                              status="pending_approval", approved_by_farmer=False)
    session.add(p)
    await session.commit()
    return p.proposal_id


@pytest.mark.asyncio
async def test_only_the_owning_farm_links_reads_or_writes(client):
    http, session, monkeypatch = client
    team, judge = await _farm(http, "Team"), await _farm(http, "Judge")
    calendar_service.set_calendar_owner(team)

    # A judge's phone can neither start a link nor read/write the team calendar.
    assert (await http.get(f"/api/calendar/auth-url?farm_id={judge}")).status_code == 409
    assert (await http.get(f"/api/calendar/events?farm_id={judge}")).status_code == 403
    assert (await http.post(f"/api/calendar/events?farm_id={judge}", json={
        "title": "x", "start_iso": "2026-09-29T08:00:00+08:00"})).status_code == 403
    assert (await http.delete(f"/api/calendar/google?farm_id={judge}")).status_code == 403
    status = (await http.get(f"/api/calendar/status?farm_id={judge}")).json()
    assert status["connected"] is False and status["linked_elsewhere"] is True

    # The judge can still approve -- kept in the app, nothing sent over MCP.
    calls = []

    async def spy(**kw):
        calls.append(kw)
        return "SUCCESS: Created event 'x' (ID: e1). Link: https://cal/e1"

    monkeypatch.setattr(mcp_calendar_client, "mcp_create_calendar_event", spy)
    pid = await _proposal(session, judge)
    r = (await http.post(f"/api/calendar/proposals/{pid}/approve", json={"farmer_confirmed": True})).json()
    assert r["status"] == "approved" and r["approved_by_farmer"] and r["html_link"] is None
    assert calls == []

    # The owner's approval goes through MCP to Google.
    pid = await _proposal(session, team)
    r = (await http.post(f"/api/calendar/proposals/{pid}/approve", json={"farmer_confirmed": True})).json()
    assert r["status"] == "deployed" and r["html_link"] == "https://cal/e1" and len(calls) == 1
    assert (await http.get(f"/api/calendar/status?farm_id={team}")).json()["connected"] is True


@pytest.mark.asyncio
async def test_demo_farm_can_never_own_google(client):
    http, _, _ = client
    demo = await _farm(http, "Kebun Demo PepperDex")
    assert calendar_service.get_calendar_owner() is None  # unclaimed
    assert (await http.get(f"/api/calendar/auth-url?farm_id={demo}")).status_code == 409


@pytest.mark.asyncio
async def test_demo_session_hands_out_the_seeded_farm(client):
    http, _, _ = client
    assert (await http.get("/demo-session")).status_code == 404
    demo = await _farm(http, "Kebun Demo PepperDex")
    body = (await http.get("/demo-session")).json()
    assert body["farm"]["farm_id"] == demo and body["user"]["user_id"]
