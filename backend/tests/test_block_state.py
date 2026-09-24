"""Block state model (docs/PROJECT_SPEC.md "Block state model"), 2026-09-24:
states only ever escalated, so a block harmed once stayed harmed forever and
a healthy re-diagnosis changed nothing on the Farm tab."""
from datetime import datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.db import get_session
from app.main import app
from app.models.base import Base
from app.models.core import Block
from app.routers import diagnosis as diagnosis_router
from app.schemas.diagnosis import DiagnoseLeafResult


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(settings, "media_root", str(tmp_path))
    (tmp_path / "p.jpg").write_bytes(b"x")
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        async def _override():
            yield session

        app.dependency_overrides[get_session] = _override
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as http:
            yield http, session, monkeypatch
        app.dependency_overrides.clear()
    await engine.dispose()


def _classifier(cls: str, conf: float):
    def fake(observation_id, path, target):
        return DiagnoseLeafResult(
            observation_id=observation_id, predicted_class=cls, confidence=conf, all_scores={},
            below_threshold=conf < 0.6, model_version="t",
        )
    return fake


async def _photo(http, monkeypatch, user_id, block_id, cycle_id, cls, conf=0.9):
    monkeypatch.setattr(diagnosis_router, "diagnose_leaf", _classifier(cls, conf))
    r = await http.post("/observations", json={
        "cycle_id": cycle_id, "block_id": block_id, "user_id": user_id, "image_uri": "/media/p.jpg",
        "image_hash": "h", "capture_target": "collar" if "collar" in cls else "leaf",
        "captured_at": datetime(2026, 9, 24, 1).isoformat(), "force_accept": True,
    })
    assert r.status_code in (200, 201), r.text


async def _cycle(http, farm_id):
    r = await http.post(f"/farms/{farm_id}/diagnosis-cycles", json={"trigger_reason": "user_initiated"})
    assert r.status_code == 201, r.text
    return r.json()["cycle_id"]


@pytest.mark.asyncio
async def test_new_cycle_diagnosis_overrides_old_state_both_ways(client):
    http, session, monkeypatch = client
    user = (await http.post("/users", json={"display_name": "N", "district": "Sibu"})).json()
    farm = (await http.post("/farms", json={"user_id": user["user_id"], "name": "F",
                                            "centroid_lat": 2.3, "centroid_lon": 111.8})).json()
    block = Block(farm_id=farm["farm_id"], label="A", photo_uri="x", centroid_lat=2.3,
                  centroid_lon=111.8, elevation_rank=1)
    session.add(block)
    await session.commit()

    c1 = await _cycle(http, farm["farm_id"])
    await _photo(http, monkeypatch, user["user_id"], block.block_id, c1, "collar_lesion")
    await session.refresh(block)
    assert block.current_state == "harmed"

    # Next cycle: a confident healthy result is ground truth -> protected.
    c2 = await _cycle(http, farm["farm_id"])
    await _photo(http, monkeypatch, user["user_id"], block.block_id, c2, "healthy_collar", 0.93)
    await session.refresh(block)
    assert block.current_state == "protected"

    # Within the same cycle, a retake never downgrades (worst-class-wins).
    await _photo(http, monkeypatch, user["user_id"], block.block_id, c2, "foliar_yellowing")
    await session.refresh(block)
    assert block.current_state == "alerted"
    await _photo(http, monkeypatch, user["user_id"], block.block_id, c2, "healthy_leaf", 0.95)
    await session.refresh(block)
    assert block.current_state == "alerted"


@pytest.mark.asyncio
async def test_unsure_or_unrelated_photo_is_not_evidence(client):
    http, session, monkeypatch = client
    user = (await http.post("/users", json={"display_name": "N", "district": "Sibu"})).json()
    farm = (await http.post("/farms", json={"user_id": user["user_id"], "name": "F",
                                            "centroid_lat": 2.3, "centroid_lon": 111.8})).json()
    block = Block(farm_id=farm["farm_id"], label="A", photo_uri="x", centroid_lat=2.3,
                  centroid_lon=111.8, elevation_rank=1, current_state="harmed")
    session.add(block)
    await session.commit()

    c = await _cycle(http, farm["farm_id"])
    await _photo(http, monkeypatch, user["user_id"], block.block_id, c, "healthy_leaf", 0.43)
    await session.refresh(block)
    assert block.current_state == "harmed", "a 43% 'healthy' must not clear a harmed block"
    await _photo(http, monkeypatch, user["user_id"], block.block_id, c, "unrelated", 0.9)
    await session.refresh(block)
    assert block.current_state == "harmed"


@pytest.mark.asyncio
async def test_phone_utc_timestamp_is_stored_as_kuching_time(client):
    """The phone sends toISOString() (UTC, 'Z'). SQLite used to keep the UTC
    digits and drop the zone, so photos read 8 h early next to server times."""
    from sqlalchemy import select as _select

    from app.models.base import KUCHING_TZ
    from app.models.diagnosis import Observation

    http, session, monkeypatch = client
    user = (await http.post("/users", json={"display_name": "N", "district": "Sibu"})).json()
    farm = (await http.post("/farms", json={"user_id": user["user_id"], "name": "F",
                                            "centroid_lat": 2.3, "centroid_lon": 111.8})).json()
    block = Block(farm_id=farm["farm_id"], label="A", photo_uri="x", centroid_lat=2.3,
                  centroid_lon=111.8, elevation_rank=1)
    session.add(block)
    await session.commit()
    monkeypatch.setattr(diagnosis_router, "diagnose_leaf", _classifier("healthy_leaf", 0.9))
    r = await http.post("/observations", json={
        "block_id": block.block_id, "user_id": user["user_id"], "image_uri": "/media/p.jpg",
        "image_hash": "h", "capture_target": "leaf", "captured_at": "2026-09-23T15:31:00.000Z",
    })
    assert r.status_code in (200, 201), r.text

    session.expire_all()
    obs = (await session.execute(_select(Observation))).scalars().one()
    assert obs.captured_at.tzinfo is not None
    local = obs.captured_at.astimezone(KUCHING_TZ)
    assert (local.hour, local.minute) == (23, 31)
    # And the raw stored wall-clock is Kuching, so SQL ordering against
    # server-written times (now_kuching) is consistent.
    raw = (await session.execute(__import__("sqlalchemy").text("select captured_at from observations"))).scalar()
    assert str(raw).startswith("2026-09-23 23:31")
