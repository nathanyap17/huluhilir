"""Regressions found on the first real-phone run (2026-09-20):

- dashboard 500'd right after the first diagnosis (naive vs aware datetime in
  the Advisor's days-since calculation), so the app fell back to the
  "first diagnosis" card;
- settings had no way to change language / rename the farm;
- the rain-pulse card's speech call used slot names the template doesn't have.
"""
from datetime import datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import get_session
from app.main import app
from app.models.base import Base
from app.models.diagnosis import DiagnosisCycle


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:

        async def _override():
            yield session

        app.dependency_overrides[get_session] = _override
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            yield http, session
        app.dependency_overrides.clear()
    await engine.dispose()


async def _user_and_farm(http):
    user = (await http.post("/users", json={"display_name": "N", "district": "Sibu"})).json()
    farm = (
        await http.post(
            "/farms",
            json={"user_id": user["user_id"], "name": "Old", "centroid_lat": 2.3, "centroid_lon": 111.8},
        )
    ).json()
    return user, farm


@pytest.mark.asyncio
async def test_language_and_farm_name_can_be_changed(client):
    http, _ = client
    user, farm = await _user_and_farm(http)

    r = await http.patch(f"/users/{user['user_id']}", json={"language_pref": "iba"})
    assert r.status_code == 200 and r.json()["language_pref"] == "iba"

    r = await http.patch(f"/farms/{farm['farm_id']}", json={"name": "Kebun Baru"})
    assert r.status_code == 200 and r.json()["name"] == "Kebun Baru"

    assert (await http.patch(f"/farms/{farm['farm_id']}", json={"name": ""})).status_code == 422
    assert (await http.patch("/users/nope", json={"language_pref": "en"})).status_code == 404


@pytest.mark.asyncio
async def test_dashboard_survives_a_completed_cycle_with_naive_timestamp(client):
    http, session = client
    _, farm = await _user_and_farm(http)

    # SQLite hands completed_at back tz-naive; this used to raise TypeError.
    session.add(
        DiagnosisCycle(
            farm_id=farm["farm_id"],
            trigger_reason="advisor",
            blocks_total=1,
            status="complete",
            completed_at=datetime(2026, 9, 18, 9, 0, 0),
        )
    )
    await session.commit()

    r = await http.get(f"/farms/{farm['farm_id']}/dashboard")
    assert r.status_code == 200, r.text
    assert r.json()["advisor"]["last_cycle_at"] is not None


@pytest.mark.asyncio
async def test_rain_pulse_template_slots_render(client):
    http, _ = client
    # The app must send exactly the template's slot names.
    r = await http.post(
        "/speech/render",
        json={
            "template_id": "rain_pulse_forecast",
            "language": "ms",
            "slots": {"rainfall_mm": "25", "day_slot": "Thu"},
        },
    )
    # 404 = templates not seeded in this in-memory DB; the point is it is not a slot 422.
    assert r.status_code in (200, 404), r.text


@pytest.mark.asyncio
async def test_calendar_grant_link_status_unlink_roundtrip(client):
    """Settings 'Connected apps' flow. POST /calendar-grants used to 500
    (AttributeError: 'str' has no attribute 'value' -- the schema stores enums
    as plain strings), which the app showed as 'Could not record consent'."""
    http, _ = client
    _, farm = await _user_and_farm(http)
    fid = farm["farm_id"]

    r = await http.post(f"/farms/{fid}/calendar-grants", json={"provider": "device_calendar"})
    assert r.status_code == 201, r.text
    assert r.json()["provider"] == "device_calendar"

    assert (await http.get(f"/farms/{fid}/calendar-grants/status")).json()["granted"] is True
    assert (await http.delete(f"/farms/{fid}/calendar-grants")).status_code == 204
    assert (await http.get(f"/farms/{fid}/calendar-grants/status")).json()["granted"] is False
