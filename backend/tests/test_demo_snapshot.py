"""Shared demo farm snapshot/restore (2026-09-25). Visitors on "Try the demo
farm" share one farm; the admin freezes it in a good state and it is put back
nightly or on demand. Restore must keep the same farm_id, touch only the demo
farm, and be refused to anyone without the admin farm's restore code."""
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import get_session
from app.main import app
from app.models.agent import AgentRun, Recommendation
from app.models.base import Base, now_kuching
from app.models.core import Block, FlowEdge, WalkSession
from app.tools.demo_snapshot import find_demo_farm, seconds_until_next
from seed.seed import seed_demo_farm, seed_treatments


@pytest_asyncio.fixture
async def ctx(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def _fk_on(dbapi_conn, _):  # behave like Postgres: enforce foreign keys
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        await seed_treatments(session)
        await seed_demo_farm(session)
        await session.commit()

        async def _override():
            yield session

        app.dependency_overrides[get_session] = _override
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            # The admin (calendar-owner) farm and its restore code.
            user = (await client.post("/users", json={"display_name": "N", "district": "Sibu"})).json()
            farm = (await client.post("/farms", json={"user_id": user["user_id"], "name": "Kebun Admin",
                                                      "centroid_lat": 2.3, "centroid_lon": 111.8})).json()
            # Read the code before pinning: once pinned, the API keeps it offline.
            code = (await client.get(f"/farms/{farm['farm_id']}/restore-code")).json()["code"]
            monkeypatch.setenv("CALENDAR_OWNER_FARM_ID", farm["farm_id"])
            yield client, session, code, farm["farm_id"]
        app.dependency_overrides.clear()
    await engine.dispose()


async def _count(session, model, **where):
    q = select(func.count()).select_from(model)
    for k, v in where.items():
        q = q.where(getattr(model, k) == v)
    return (await session.execute(q)).scalar_one()


@pytest.mark.asyncio
async def test_restore_undoes_visitor_changes_and_keeps_the_farm_id(ctx):
    http, session, code, admin_farm_id = ctx
    demo = await find_demo_farm(session)
    demo_id = demo.farm_id

    # A walk session linked from the farm row (farms <-> walk_sessions cycle).
    ws = WalkSession(farm_id=demo_id)
    session.add(ws)
    await session.flush()
    demo.walk_session_id = ws.walk_session_id
    ws_id = ws.walk_session_id
    await session.commit()

    blocks_before = {b.block_id: b.current_state for b in (await session.execute(
        select(Block).where(Block.farm_id == demo_id))).scalars()}
    runs_before = await _count(session, AgentRun, farm_id=demo_id)
    edges_before = await _count(session, FlowEdge, farm_id=demo_id)

    r = await http.post("/demo/snapshot", json={"restore_code": code})
    assert r.status_code == 200 and r.json()["rows"]["blocks"] == len(blocks_before)

    # A visitor's session: a new run + recommendation, a block turned Harmed,
    # an edge lost.
    first_block = next(iter(blocks_before))
    run = AgentRun(farm_id=demo_id, trigger="manual", llm_model="visitor")
    session.add(run)
    await session.flush()
    session.add(Recommendation(run_id=run.run_id, block_id=first_block, sequence=1, action_type="inspect",
                               recommended_at=now_kuching(), reason_ms="visitor"))
    (await session.get(Block, first_block)).current_state = "harmed"
    edge = (await session.execute(select(FlowEdge).where(FlowEdge.farm_id == demo_id))).scalars().first()
    await session.delete(edge)
    await session.commit()
    assert await _count(session, AgentRun, farm_id=demo_id) == runs_before + 1

    admin_blocks = await _count(session, Block, farm_id=admin_farm_id)

    r = await http.post("/demo/restore", json={"restore_code": code.replace("-", "").lower()})
    assert r.status_code == 200
    session.expire_all()

    demo_after = await find_demo_farm(session)
    assert demo_after.farm_id == demo_id  # phones on the demo keep working
    assert demo_after.walk_session_id == ws_id
    assert await _count(session, AgentRun, farm_id=demo_id) == runs_before
    assert await _count(session, FlowEdge, farm_id=demo_id) == edges_before
    assert await _count(session, Recommendation, reason_ms="visitor") == 0
    states = {b.block_id: b.current_state for b in (await session.execute(
        select(Block).where(Block.farm_id == demo_id))).scalars()}
    assert states == blocks_before
    assert await _count(session, Block, farm_id=admin_farm_id) == admin_blocks  # other farms untouched

    status = (await http.get("/demo/snapshot")).json()
    assert status["exists"] and status["restored_at"] is not None


@pytest.mark.asyncio
async def test_only_the_admin_code_can_capture_or_restore(ctx):
    http, _, code, _ = ctx
    for path in ("/demo/snapshot", "/demo/restore"):
        r = await http.post(path, json={"restore_code": "AAA-BBB-CCC"})
        assert r.status_code == 403
    # A real farm's code that isn't the admin farm's is refused too.
    user = (await http.post("/users", json={"display_name": "V", "district": "Sibu"})).json()
    other = (await http.post("/farms", json={"user_id": user["user_id"], "name": "Kebun Lain",
                                             "centroid_lat": 2.3, "centroid_lon": 111.8})).json()
    other_code = (await http.get(f"/farms/{other['farm_id']}/restore-code")).json()["code"]
    assert (await http.post("/demo/restore", json={"restore_code": other_code})).status_code == 403
    # Admin, but nothing captured yet.
    assert (await http.post("/demo/restore", json={"restore_code": code})).status_code == 404


def test_nightly_schedule_targets_three_am_kuching():
    kuching = timezone(timedelta(hours=8))
    assert seconds_until_next(3, datetime(2026, 9, 25, 2, 0, tzinfo=kuching)) == 3600
    assert seconds_until_next(3, datetime(2026, 9, 25, 3, 0, tzinfo=kuching)) == 24 * 3600
    assert seconds_until_next(3, datetime(2026, 9, 25, 22, 0, tzinfo=kuching)) == 5 * 3600
