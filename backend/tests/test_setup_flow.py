"""End-to-end setup flow + the non-negotiable rules the setup endpoints must
honour. These are proposal commitments, so they're tested structurally rather
than trusted to code review (pepperdex-rules skill § "Checklist").
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
        if baro_values and baro_values[i] is not None:
            payload["baro_rel_m"] = baro_values[i]
        block = (await http.post(f"/farms/{farm['farm_id']}/blocks", json=payload)).json()
        block_ids.append(block["block_id"])
    return farm, block_ids


@pytest.mark.asyncio
async def test_minimal_tier_asks_every_distinct_pair(client):
    """No barometer -> full pairwise, C(n, 2).

    This previously asserted n-1 *adjacent* pairs, which was wrong: without
    an altitude sensor the capture order is just the order the farmer walked
    in, so comparing neighbours in that arbitrary sequence establishes no
    ordering at all. Full pairwise is the honest cost, and it also makes
    contradictory answers (a > b, b > c, c > a) detectable.
    """
    http, _ = client
    farm, block_ids = await _walk_three_blocks(http, barometer=False)

    resp = (await http.get(f"/farms/{farm['farm_id']}/elevation-questions")).json()
    assert resp["elevation_tier"] == "minimal"

    n = len(block_ids)
    assert len(resp["questions"]) == n * (n - 1) // 2  # C(3,2) = 3

    # Every pair distinct, and no block ever compared against itself.
    seen = {
        frozenset((q["block_a_id"], q["block_b_id"])) for q in resp["questions"]
    }
    assert len(seen) == len(resp["questions"])
    assert all(len(pair) == 2 for pair in seen)


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
    """pepperdex-rules skill §3 -- the farmer ALWAYS wins, and the
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
    """pepperdex-rules skill §6 -- a stated proposal claim. The rain pulse and
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
    assert data["drawer"] is None  # no risk_assessments row exists without a run either
    assert len(data["terrain_nodes"]) == 3
    assert data["pending_neighbour_alerts"] == 0


@pytest.mark.asyncio
async def test_dashboard_rain_pulse_is_seven_days(client):
    """🔄 v2 -- docs/PROJECT_SPEC.md §9.1/§10: forecast_days[], not a single
    collapsed next-pulse object."""
    http, _ = client
    farm, _ = await _walk_three_blocks(http)

    data = (await http.get(f"/farms/{farm['farm_id']}/dashboard")).json()
    forecast_days = data["rain_pulse"]["forecast_days"]
    assert len(forecast_days) > 0
    for day in forecast_days:
        assert set(day.keys()) == {"date", "rainfall_mm", "is_pulse", "is_cached_fallback"}
        assert day["is_pulse"] == (day["rainfall_mm"] >= 5.0)


@pytest.mark.asyncio
async def test_dashboard_terrain_nodes_carry_rotated_coordinates(client):
    """🔄 v2 -- §9.6/§10 BlockNode.x_rot_m/y_rot_m, backend-computed and never
    persisted (docs/DATA_MODEL.md §5)."""
    http, _ = client
    farm, _ = await _walk_three_blocks(http)

    data = (await http.get(f"/farms/{farm['farm_id']}/dashboard")).json()
    for node in data["terrain_nodes"]:
        assert isinstance(node["x_rot_m"], (int, float))
        assert isinstance(node["y_rot_m"], (int, float))


@pytest.mark.asyncio
async def test_no_land_boundary_field_is_accepted(client):
    """pepperdex-rules skill §4 -- NCR land is legally sensitive; only
    elevation_rank ordering and point centroids are ever stored."""
    http, _ = client
    farm, _ = await _walk_three_blocks(http)

    resp = await http.get(f"/farms/{farm['farm_id']}/dashboard")
    payload = resp.text.lower()
    for forbidden in ("boundary", "polygon", "geometry", "parcel", "ownership", "title_deed"):
        assert forbidden not in payload


async def _walk_with_pressure(http, pressures):
    """Barometer phone sending raw pressure per block (build 22+)."""
    user = (await http.post("/users", json={"display_name": "N", "district": "Julau"})).json()
    farm = (await http.post("/farms", json={
        "user_id": user["user_id"], "name": "Kebun Baro",
        "centroid_lat": 1.5533, "centroid_lon": 110.3592, "barometer_available": True,
    })).json()
    positions = [(1.5540, 110.3588), (1.5535, 110.3592), (1.5528, 110.3596)]
    ids = []
    for i, ((lat, lon), p) in enumerate(zip(positions, pressures)):
        block = (await http.post(f"/farms/{farm['farm_id']}/blocks", json={
            "label": f"Blok {i + 1}", "photo_uri": "/media/t.jpg",
            "position_samples": [[lat, lon], [lat, lon + 0.00001]], "drainage": "fair",
            "pressure_hpa": p,
        })).json()
        ids.append((block["block_id"], block["baro_rel_m"]))
    return farm, ids


@pytest.mark.asyncio
async def test_server_derives_altitude_from_raw_pressure_and_skips_questions(client):
    """2026-09-27: altitude is computed on the server against the walk's
    baseline, so a restarted app can't lose it. Well-separated blocks need
    no questions at all, and the ranking follows the barometer."""
    http, _ = client
    # ~1 hPa is ~8 m: block 2 highest, block 1 middle (baseline), block 3 lowest.
    farm, ids = await _walk_with_pressure(http, [1000.0, 999.0, 1000.6])
    (b1, h1), (b2, h2), (b3, h3) = ids
    assert h1 == 0.0 and h2 > 7.5 and h3 < -4.5

    q = (await http.get(f"/farms/{farm['farm_id']}/elevation-questions")).json()
    assert q["barometer_used"] is True and q["questions"] == []

    r = (await http.post(f"/farms/{farm['farm_id']}/resolve-elevation", json={"answers": []})).json()
    assert r["ranks"][b2] == 1 and r["ranks"][b1] == 2 and r["ranks"][b3] == 3


@pytest.mark.asyncio
async def test_farmer_answer_on_a_close_pair_does_not_outrank_a_clearly_higher_block(client):
    """2026-09-27: a farmer's answer about two near-equal blocks used to lift
    the answered block above one the barometer put metres higher."""
    http, _ = client
    farm, block_ids = await _walk_three_blocks(http, barometer=True, baro_values=[10.0, 5.0, 4.5])
    # Only the 0.5 m pair (blocks 2 and 3) is asked; the farmer says 3 is higher.
    answers = [{"block_a_id": block_ids[1], "block_b_id": block_ids[2], "answer": "b_higher"}]
    r = (await http.post(f"/farms/{farm['farm_id']}/resolve-elevation", json={"answers": answers})).json()
    assert r["ranks"][block_ids[0]] == 1  # still highest, 5 m above the others
    assert r["ranks"][block_ids[2]] == 2 and r["ranks"][block_ids[1]] == 3  # farmer wins the close pair


@pytest.mark.asyncio
async def test_incomplete_barometer_readings_fall_back_to_asking_every_pair(client):
    http, _ = client
    farm, block_ids = await _walk_three_blocks(http, barometer=True, baro_values=[10.0, None, 2.0])
    q = (await http.get(f"/farms/{farm['farm_id']}/elevation-questions")).json()
    assert q["barometer_used"] is False
    assert len(q["questions"]) == 3
