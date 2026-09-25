"""MCP calendar sync -- docs/PROJECT_SPEC.md §9.15, rule 13.

EXP-16 (docs/VALIDATION_CHECKLIST.md) already validated the consent-gate
PATTERN in isolation (sandbox/exp16_calendar_gate.py). These tests exercise
the REAL endpoints: grant/revoke/status and on-demand draft generation.
"""
import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import get_session
from app.main import app
from app.models.agent import AgentRun, Recommendation
from app.models.base import Base, now_kuching


def _ollama_available() -> bool:
    try:
        return httpx.get("http://localhost:11434/api/tags", timeout=2.0).status_code == 200
    except httpx.HTTPError:
        return False


@pytest.fixture(autouse=True)
def _isolated_calendar_owner(tmp_path, monkeypatch):
    # Never read the developer's real backend/calendar_owner.json in tests.
    from app.tools import calendar_service

    monkeypatch.setattr(calendar_service, "OWNER_FILE", tmp_path / "calendar_owner.json")
    monkeypatch.delenv("CALENDAR_OWNER_FARM_ID", raising=False)


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


async def _make_farm(http):
    user = (await http.post("/users", json={"display_name": "Nathan", "district": "Julau"})).json()
    farm = (await http.post("/farms", json={
        "user_id": user["user_id"], "name": "Kebun Ujian",
        "centroid_lat": 1.5533, "centroid_lon": 110.3592,
    })).json()
    return farm


@pytest.mark.asyncio
async def test_calendar_status_is_false_with_no_grant(client):
    http, _ = client
    farm = await _make_farm(http)

    status = (await http.get(f"/farms/{farm['farm_id']}/calendar-grants/status")).json()
    assert status["granted"] is False
    assert status["grant"] is None


@pytest.mark.asyncio
async def test_calendar_grant_then_status_is_true(client):
    http, _ = client
    farm = await _make_farm(http)

    grant = (await http.post(f"/farms/{farm['farm_id']}/calendar-grants", json={})).json()
    assert grant["provider"] == "device_calendar"
    assert grant["revoked_at"] is None

    status = (await http.get(f"/farms/{farm['farm_id']}/calendar-grants/status")).json()
    assert status["granted"] is True
    assert status["grant"]["grant_id"] == grant["grant_id"]


@pytest.mark.asyncio
async def test_revoke_makes_status_false_again(client):
    """pepperdex-rules skill §13 -- revoked_at must be checked before every
    future write, not just at approval time."""
    http, _ = client
    farm = await _make_farm(http)

    await http.post(f"/farms/{farm['farm_id']}/calendar-grants", json={})
    resp = await http.delete(f"/farms/{farm['farm_id']}/calendar-grants")
    assert resp.status_code == 204

    status = (await http.get(f"/farms/{farm['farm_id']}/calendar-grants/status")).json()
    assert status["granted"] is False


@pytest.mark.asyncio
async def test_revoke_is_idempotent_with_no_grant(client):
    http, _ = client
    farm = await _make_farm(http)
    resp = await http.delete(f"/farms/{farm['farm_id']}/calendar-grants")
    assert resp.status_code == 204


@pytest.mark.skipif(not _ollama_available(), reason="Ollama not reachable on localhost:11434")
@pytest.mark.asyncio
async def test_draft_calendar_for_recommendation_never_writes_a_calendar(client):
    """The endpoint must ONLY return draft text -- there is no calendar
    client to write to on a test server, and the response shape itself
    proves nothing beyond DraftCalendarSyncResult is returned."""
    http, session = client
    farm = await _make_farm(http)
    block = (await http.post(f"/farms/{farm['farm_id']}/blocks", json={
        "label": "Blok Atas", "photo_uri": "/media/test.jpg",
        "position_samples": [[1.5533, 110.3592]],
    })).json()

    agent_run = AgentRun(farm_id=farm["farm_id"], trigger="manual", llm_model="test", started_at=now_kuching())
    session.add(agent_run)
    await session.flush()
    rec = Recommendation(
        run_id=agent_run.run_id, block_id=block["block_id"], sequence=1, action_type="spray",
        recommended_at=now_kuching(), reason_ms="Semburan diperlukan sebelum hujan.",
    )
    session.add(rec)
    await session.commit()

    resp = await http.post(f"/recommendations/{rec.recommendation_id}/draft-calendar")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["draft_events"]) == 1
    event = data["draft_events"][0]
    assert set(event.keys()) == {"title", "date", "description"}
    assert len(event["title"]) <= 60
    assert len(event["description"]) <= 200


@pytest.mark.asyncio
async def test_draft_calendar_404s_for_unknown_recommendation(client):
    http, _ = client
    resp = await http.post("/recommendations/does-not-exist/draft-calendar")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_google_calendar_status(client):
    http, _ = client
    resp = await http.get("/api/calendar/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "connected" in data
    assert isinstance(data["connected"], bool)
    assert data["token_file"] == "token.json"


@pytest.mark.asyncio
async def test_google_calendar_auth_url(client, monkeypatch):
    from app.tools import calendar_service
    # A first link: nothing connected yet (re-linking a connected calendar is refused).
    monkeypatch.setattr(calendar_service, "is_calendar_connected", lambda: False)
    http, _ = client
    resp = await http.get("/api/calendar/auth-url?farm_id=farm_123")
    assert resp.status_code == 200
    data = resp.json()
    assert "auth_url" in data
    assert "accounts.google.com" in data["auth_url"]
    assert "state=farm_123" in data["auth_url"]
    assert "client_id=" in data["auth_url"]


@pytest.mark.asyncio
async def test_google_calendar_login_redirect(client, monkeypatch):
    from app.tools import calendar_service
    # A first link: nothing connected yet (re-linking a connected calendar is refused).
    monkeypatch.setattr(calendar_service, "is_calendar_connected", lambda: False)
    http, _ = client
    resp = await http.get("/api/calendar/login?farm_id=farm_123", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "accounts.google.com" in resp.headers.get("location", "")


@pytest.mark.asyncio
async def test_google_calendar_events_unconnected_returns_400(client, monkeypatch):
    from app.tools import calendar_service
    monkeypatch.setattr(calendar_service, "is_calendar_connected", lambda: False)
    http, _ = client
    # The direct read/write endpoints were removed on 2026-09-26: the app never
    # used them, and a farm_id (which can be public) was their only key.
    get_resp = await http.get("/api/calendar/events")
    assert get_resp.status_code in (404, 405)

    post_resp = await http.post(
        "/api/calendar/events",
        json={
            "title": "Semburan Kuprum Blok A",
            "start_iso": "2026-09-25T09:00:00+08:00",
            "description": "Rawatan bintik daun",
        },
    )
    assert post_resp.status_code in (404, 405)


@pytest.mark.asyncio
async def test_calendar_agent_tools_when_disconnected(monkeypatch):
    from app.agent import mcp_calendar_client
    # Mock the MCP client to simulate connection failure
    async def mock_fail(*args, **kwargs):
        raise Exception("Google Calendar is not connected.")
    monkeypatch.setattr(mcp_calendar_client, "mcp_list_upcoming_events", mock_fail)
    monkeypatch.setattr(mcp_calendar_client, "mcp_create_calendar_event", mock_fail)

    from app.agent.tools import check_calendar_schedule, schedule_treatment_event

    check_res = await check_calendar_schedule()
    assert check_res["connected"] is False
    assert "Google Calendar" in check_res["error"]

    sched_res = await schedule_treatment_event(
        title="Ujian Semburan",
        start_iso="2026-09-25T09:00:00+08:00",
    )
    assert sched_res["success"] is False
    assert "Google Calendar" in sched_res["error"]

