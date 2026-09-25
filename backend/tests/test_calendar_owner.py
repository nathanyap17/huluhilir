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
    assert (await http.get(f"/api/calendar/events?farm_id={judge}")).status_code in (404, 405)  # removed
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


@pytest.mark.asyncio
async def test_agent_calendar_reads_are_limited_to_the_owner_farm(monkeypatch):
    """Found 2026-09-26: the agent's read tools ignored which farm the run was
    for, so a run on the shared demo farm could read the team's Google
    Calendar. Reads now go through farm_may_write, like every other path."""
    from app.agent import mcp_calendar_client
    from app.agent import tools as agent_tools
    from app.tools import calendar_service

    calls = []

    async def fake_list(max_results=10):
        calls.append("list")
        return "PRIVATE-EVENT"

    async def fake_avail(start_iso, end_iso):
        calls.append("avail")
        return "PRIVATE-FREEBUSY"

    monkeypatch.setattr(mcp_calendar_client, "mcp_list_upcoming_events", fake_list)
    monkeypatch.setattr(mcp_calendar_client, "mcp_check_availability", fake_avail)
    monkeypatch.setenv("CALENDAR_OWNER_FARM_ID", "OWNER")
    monkeypatch.setattr(calendar_service, "is_calendar_connected", lambda: True)

    def tools_for(farm_id):
        return {t.name: t.func for t in agent_tools.build_tools(None, farm_id)}

    visitor = tools_for("DEMO-OR-VISITOR")
    for result in (
        await visitor["check_calendar_schedule"](),
        await visitor["check_calendar_availability"]("2026-09-26T08:00", "2026-09-26T09:00"),
    ):
        assert result["connected"] is False and "PRIVATE" not in str(result)
    assert calls == []  # the calendar was never touched

    owner = tools_for("OWNER")
    assert (await owner["check_calendar_schedule"]())["mcp_output"] == "PRIVATE-EVENT"
    assert (await owner["check_calendar_availability"]("a", "b"))["mcp_output"] == "PRIVATE-FREEBUSY"
    assert calls == ["list", "avail"]


@pytest.mark.asyncio
async def test_a_public_owner_farm_id_unlocks_nothing(client):
    """Found 2026-09-26: the owner farm's id is committed in the public repo.
    With the owner pinned by the deployment, that id alone must not read or
    write the calendar, re-link it, unlink it, or reveal/rotate the restore
    code -- while the admin, who holds the code, can still restore the farm."""
    http, session, monkeypatch = client
    team = await _farm(http, "Team")
    code = (await http.get(f"/farms/{team}/restore-code")).json()["code"]  # before the pin
    monkeypatch.setenv("CALENDAR_OWNER_FARM_ID", team)

    for method, path in [
        ("get", f"/api/calendar/events?farm_id={team}"),
        ("post", f"/api/calendar/events?farm_id={team}"),
        ("get", f"/api/calendar/mcp/events?farm_id={team}"),
        ("post", f"/api/calendar/mcp/events?farm_id={team}"),
    ]:
        assert (await getattr(http, method)(path)).status_code in (404, 405), path
    assert (await http.get(f"/api/calendar/auth-url?farm_id={team}")).status_code == 409  # no re-link
    assert (await http.get(f"/api/calendar/login?farm_id={team}")).status_code == 409
    assert (await http.delete(f"/api/calendar/google?farm_id={team}")).status_code == 403
    assert (await http.get(f"/farms/{team}/restore-code")).status_code == 403
    assert (await http.post(f"/farms/{team}/restore-code/rotate")).status_code == 403
    assert (await http.post(f"/farms/{team}/calendar-proposals", json={
        "title": "anything", "start_iso": "2026-09-29T08:00:00+08:00"})).status_code == 403

    # The admin, holding the code, still gets the farm back.
    r = await http.post("/restore", json={"code": code})
    assert r.status_code == 200 and r.json()["farm"]["farm_id"] == team

    # Other farms are unaffected: their own code still shows and rotates.
    other = await _farm(http, "Other")
    assert (await http.get(f"/farms/{other}/restore-code")).status_code == 200
    assert (await http.post(f"/farms/{other}/restore-code/rotate")).status_code == 200
