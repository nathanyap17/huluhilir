"""End-to-end setup flow + the non-negotiable rules the setup endpoints must
honour. These are proposal commitments, so they're tested structurally rather
than trusted to code review (huluhilir-rules skill § "Checklist").
"""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import get_session
from app.main import app
from app.models.base import Base
from app.models.core import Block, ElevationConflict, FlowEdge


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # One session for the whole test so in-memory SQLite state persists across
    # requests (a new connection would get a fresh empty database).
    async with session_factory() as session:
        async def _override():
            yield session

        app.dependency_overrides[get_session] = _override
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as http:
            yield http, session
        app.dependency_overrides.clear()
    await engine.dispose()


async def _walk_three_blocks(http, barometer: bool = False, baro_values=None):
    user = (await http.post("/users", json={"display_name": "Nathan", "district": "Julau"})).json()
    farm = (await http.post("/farms", json={
        "user_id": user["user_id"], "name": "Kebun Ujian",
        "centroid_lat": 1.5533, "centroid_lon": 110.3592,
        "barometer_available": barometer,
    })).json()

    positions = [(1.5540, 110.3588), (1.5535, 110.3592), (1.5528, 110.3596)]
    block_ids = []
    for i, (lat, lon) in enumerate(positions):
        payload = {
            "label": f"Blok {i + 1}",
            "photo_uri": "/media/test.jpg",
            "position_samples": [[lat, lon], [lat + 0.00001, lon], [lat, lon + 0.00001]],
            "drainage": "fair",
        }
        if baro_values:
            payload["baro_rel_m"] = baro_values[i]
        block = (await http.post(f"/farms/{farm['farm_id']}/blocks", json=payload)).json()
        block_ids.append(block["block_id"])
    return farm, block_ids


@pytest.mark.asyncio
async def test_minimal_tier_asks_all_adjacent_pairs(client):
    http, _ = client
    farm, block_ids = await _walk_three_blocks(http, barometer=False)

    resp = (await http.get(f"/farms/{farm['farm_id']}/elevation-questions")).json()
    assert resp["elevation_tier"] == "minimal"
    assert len(resp["questions"]) == 2  # n-1 for 3 blocks


@pytest.mark.asyncio
async def test_optimised_tier_only_asks_where_sensor_cannot_separate(client):
    """Δh >= 2.0 m -> accept sensor; Δh < 2.0 m -> ask (PROJECT_SPEC §4)."""
    http, _ = client
    # b1=10.0, b2=9.5 (gap 0.5 -> ambiguous), b3=2.0 (gap 7.5 -> clear)
    farm, block_ids = await _walk_three_blocks(http, barometer=True, baro_values=[10.0, 9.5, 2.0])

    resp = (await http.get(f"/farms/{farm['farm_id']}/elevation-questions")).json()
    assert resp["elevation_tier"] == "optimised"
    assert len(resp["questions"]) == 1  # only the 0.5 m pair


@pytest.mark.asyncio
async def test_resolve_elevation_builds_an_acyclic_graph(client):
    http, session = client
    farm, block_ids = await _walk_three_blocks(http)

    answers = [
        {"block_a_id": block_ids[0], "block_b_id": block_ids[1], "answer": "a_higher"},
        {"block_a_id": block_ids[1], "block_b_id": block_ids[2], "answer": "a_higher"},
    ]
    result = (await http.post(f"/farms/{farm['farm_id']}/resolve-elevation", json={"answers": answers})).json()

    assert result["setup_completed"] is True
    assert result["edges_created"] > 0

    blocks = {b.block_id: b for b in (await session.execute(select(Block))).scalars().all()}
    edges = (await session.execute(select(FlowEdge))).scalars().all()

    # The invariant compute_spread depends on: every edge runs strictly downhill.
    for edge in edges:
        assert blocks[edge.from_block_id].elevation_rank < blocks[edge.to_block_id].elevation_rank

    # elevation_rank must be unique per farm -- ties break the graph.
    ranks = [b.elevation_rank for b in blocks.values()]
    assert len(ranks) == len(set(ranks))


@pytest.mark.asyncio
async def test_farmer_answer_overrides_barometer_and_logs_the_conflict(client):
    """huluhilir-rules skill §3 -- the farmer ALWAYS wins, and the
    disagreement is recorded rather than silently resolved."""
    http, session = client
    # Barometer says block 1 is LOWER than block 2 (1.0 vs 5.0)...
    farm, block_ids = await _walk_three_blocks(http, barometer=True, baro_values=[1.0, 5.0, 0.5])

    # ...but the farmer says block 1 is higher. Farmer wins.
    answers = [{"block_a_id": block_ids[0], "block_b_id": block_ids[1], "answer": "a_higher"}]
    result = (await http.post(f"/farms/{farm['farm_id']}/resolve-elevation", json={"answers": answers})).json()

    assert result["conflicts_logged"] == 1
    assert result["ranks"][block_ids[0]] < result["ranks"][block_ids[1]]  # 1 = highest

    conflict = (await session.execute(select(ElevationConflict))).scalars().one()
    assert conflict.resolution == "farmer"
    assert conflict.farmer_says == "a_higher"
    assert conflict.barometer_says == "b_higher"


@pytest.mark.asyncio
async def test_dashboard_works_with_zero_photographs(client):
    """huluhilir-rules skill §6 -- a stated proposal claim. The rain pulse and
    Advisor must render on a farm with no observations, no diagnosis cycle,
    and no agent run."""
    http, _ = client
    farm, block_ids = await _walk_three_blocks(http)
    await http.post(f"/farms/{farm['farm_id']}/resolve-elevation", json={"answers": [
        {"block_a_id": block_ids[0], "block_b_id": block_ids[1], "answer": "a_higher"},
        {"block_a_id": block_ids[1], "block_b_id": block_ids[2], "answer": "a_higher"},
    ]})

    resp = await http.get(f"/farms/{farm['farm_id']}/dashboard")
    assert resp.status_code == 200
    data = resp.json()

    assert data["rain_pulse"] is not None
    assert data["advisor"] is not None
    assert data["top_action"] is None  # no agent run has happened
    assert len(data["terrain_nodes"]) == 3
    assert data["pending_neighbour_alerts"] == 0


@pytest.mark.asyncio
async def test_no_land_boundary_field_is_accepted(client):
    """huluhilir-rules skill §4 -- NCR land is legally sensitive; only
    elevation_rank ordering and point centroids are ever stored."""
    http, _ = client
    farm, _ = await _walk_three_blocks(http)

    resp = await http.get(f"/farms/{farm['farm_id']}/dashboard")
    payload = resp.text.lower()
    for forbidden in ("boundary", "polygon", "geometry", "parcel", "ownership", "title_deed"):
        assert forbidden not in payload
