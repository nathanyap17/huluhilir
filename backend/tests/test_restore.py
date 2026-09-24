"""Restore my farm / demo lock / farm list privacy (2026-09-24). There are no
accounts: a phone's saved farm_id is its only link to a farm, so a new or
reset phone needs a restore code to get back -- and the farm list must not
hand out every farm_id to anyone who asks."""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import get_session
from app.main import app
from app.models.base import Base


@pytest_asyncio.fixture
async def http():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        async def _override():
            yield session

        app.dependency_overrides[get_session] = _override
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            yield client
        app.dependency_overrides.clear()
    await engine.dispose()


async def _farm(http, name):
    user = (await http.post("/users", json={"display_name": "N", "district": "Sibu"})).json()
    farm = (await http.post("/farms", json={"user_id": user["user_id"], "name": name,
                                            "centroid_lat": 2.3, "centroid_lon": 111.8})).json()
    return user["user_id"], farm["farm_id"]


@pytest.mark.asyncio
async def test_restore_code_brings_the_same_farm_back_and_can_be_rotated(http):
    user_id, farm_id = await _farm(http, "Kebun Saya")
    code = (await http.get(f"/farms/{farm_id}/restore-code")).json()["code"]
    assert len(code) == 11 and code[3] == "-" and code[7] == "-"
    assert (await http.get(f"/farms/{farm_id}/restore-code")).json()["code"] == code  # stable

    # Typed sloppily on the new phone: lowercase, no dashes -> still works.
    r = (await http.post("/restore", json={"code": code.replace("-", "").lower()})).json()
    assert r["farm"]["farm_id"] == farm_id and r["user"]["user_id"] == user_id and r["is_demo"] is False

    new = (await http.post(f"/farms/{farm_id}/restore-code/rotate")).json()["code"]
    assert new != code
    assert (await http.post("/restore", json={"code": code})).status_code == 404  # old code dead
    assert (await http.post("/restore", json={"code": new})).status_code == 200


@pytest.mark.asyncio
async def test_wrong_code_reveals_nothing(http):
    await _farm(http, "Kebun Saya")
    r = await http.post("/restore", json={"code": "AAA-BBB-CCC"})
    assert r.status_code == 404 and r.json()["detail"] == "restore code not recognised"


@pytest.mark.asyncio
async def test_demo_farm_is_locked_and_farm_list_shows_only_it(http):
    _, demo = await _farm(http, "Kebun Demo PepperDex")
    await _farm(http, "Kebun Rahsia")

    assert (await http.get(f"/farms/{demo}/restore-code")).status_code == 403
    assert (await http.patch(f"/farms/{demo}", json={"name": "Hacked"})).status_code == 403
    assert (await http.get("/demo-session")).json()["farm"]["farm_id"] == demo

    names = [f["name"] for f in (await http.get("/farms")).json()]
    assert names == ["Kebun Demo PepperDex"], "a private farm's id must not be listed"
