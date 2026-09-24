"""build_flow_edges -- proves barometer readings (baro_rel_m) actually feed
the spread model's risk math, not just elevation ranking.

Nothing tested this before: test_spread.py exercises compute_spread with
hand-supplied flow_weight values, and test_setup_flow.py only checks
elevation_rank ordering. The path barometer data ACTUALLY takes into the
algorithm -- app/tools/graph.py's build_flow_edges computing a real
slope_ratio from two blocks' baro_rel_m, which then drives 40% of
flow_weight (W_SLOPE), which then drives compute_spread's risk -- had no
direct coverage at all.
"""
from app.models.core import Block
from app.tools.graph import build_flow_edges


def _block(block_id: str, rank: int, lat: float, lon: float, baro_rel_m: float | None, drainage: str = "fair") -> Block:
    return Block(
        block_id=block_id, farm_id="farm1", label=block_id, photo_uri="x",
        centroid_lat=lat, centroid_lon=lon, elevation_rank=rank,
        baro_rel_m=baro_rel_m, drainage=drainage,
    )


def test_steeper_barometer_slope_yields_higher_flow_weight():
    """Same horizontal distance and drainage -- only the barometer-derived
    slope differs. If baro_rel_m is wired into the calculation, the
    steeper pair's flow_weight must be strictly higher."""
    # ~111m of latitude separation at this longitude (~0.001 deg lat).
    steep = [
        _block("up", rank=1, lat=1.5010, lon=110.3000, baro_rel_m=20.0),
        _block("down", rank=2, lat=1.5000, lon=110.3000, baro_rel_m=0.0),
    ]
    gentle = [
        _block("up", rank=1, lat=1.5010, lon=110.3000, baro_rel_m=1.0),
        _block("down", rank=2, lat=1.5000, lon=110.3000, baro_rel_m=0.0),
    ]

    steep_edges = build_flow_edges("farm1", steep)
    gentle_edges = build_flow_edges("farm1", gentle)

    assert len(steep_edges) == 1 and len(gentle_edges) == 1
    assert steep_edges[0].elevation_drop_m == 20.0
    assert gentle_edges[0].elevation_drop_m == 1.0
    assert steep_edges[0].flow_weight > gentle_edges[0].flow_weight, (
        f"steeper barometer-derived slope did not increase flow_weight: "
        f"steep={steep_edges[0].flow_weight} gentle={gentle_edges[0].flow_weight}"
    )


def test_missing_barometer_data_falls_back_to_neutral_slope():
    """MINIMAL tier (no barometer) must still produce a usable edge --
    slope_ratio/elevation_drop_m stay null, flow_weight uses the documented
    neutral 0.5 slope component rather than crashing or zeroing out."""
    blocks = [
        _block("up", rank=1, lat=1.5010, lon=110.3000, baro_rel_m=None),
        _block("down", rank=2, lat=1.5000, lon=110.3000, baro_rel_m=None),
    ]
    edges = build_flow_edges("farm1", blocks)
    assert len(edges) == 1
    assert edges[0].elevation_drop_m is None
    assert edges[0].slope_ratio is None
    assert edges[0].flow_weight > 0  # still a usable, non-zero weight


def test_partial_barometer_data_also_falls_back_to_neutral():
    """Only one of the pair has a reading (e.g. it dropped out mid-walk) --
    must degrade the same way as having none, not half-compute a slope."""
    blocks = [
        _block("up", rank=1, lat=1.5010, lon=110.3000, baro_rel_m=15.0),
        _block("down", rank=2, lat=1.5000, lon=110.3000, baro_rel_m=None),
    ]
    edges = build_flow_edges("farm1", blocks)
    assert edges[0].elevation_drop_m is None
    assert edges[0].slope_ratio is None


def test_drainage_still_affects_flow_weight_independently_of_barometer():
    """Same barometer slope, different drainage -- poor drainage (pools
    water) must yield a higher flow_weight than good drainage, proving
    both inputs are actually combined, not one silently overriding the
    other."""
    good = [
        _block("up", rank=1, lat=1.5010, lon=110.3000, baro_rel_m=10.0, drainage="good"),
        _block("down", rank=2, lat=1.5000, lon=110.3000, baro_rel_m=0.0, drainage="good"),
    ]
    poor = [
        _block("up", rank=1, lat=1.5010, lon=110.3000, baro_rel_m=10.0, drainage="poor"),
        _block("down", rank=2, lat=1.5000, lon=110.3000, baro_rel_m=0.0, drainage="poor"),
    ]
    good_edges = build_flow_edges("farm1", good)
    poor_edges = build_flow_edges("farm1", poor)
    assert poor_edges[0].flow_weight > good_edges[0].flow_weight
