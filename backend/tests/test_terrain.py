"""compute_terrain_layout -- docs/PROJECT_SPEC.md §3 L2 STEP 1-2.

EXP-17 (docs/VALIDATION_CHECKLIST.md): the terrain canvas rotation must hold
for a farm NOT oriented north-south -- otherwise "hulu at top" silently
breaks for some real farms. These are pure unit tests, no DB needed.
"""
import math

from app.tools.terrain import compute_terrain_layout


def test_rotation_is_identity_with_no_edges():
    """A single block, or blocks before elevation resolution -- no flow
    direction exists yet to align to, so the projection is returned as-is."""
    blocks = [("b1", 1.5, 110.3), ("b2", 1.501, 110.301)]
    layout = compute_terrain_layout(blocks, edges=[])
    assert set(layout.keys()) == {"b1", "b2"}
    for x, y in layout.values():
        assert math.isfinite(x) and math.isfinite(y)


def test_east_west_farm_flow_points_along_plus_y_after_rotation():
    """EXP-17 -- a farm whose real slope runs due EAST (not north-south) must
    still end up with its flow direction pointing along +Y after rotation.
    If this ever regresses, the canvas would render 'hulu' sideways for any
    farm not accidentally aligned north-south."""
    # b1 (upslope) -> b2 (downslope), purely eastward: same latitude, b2 is
    # further east (larger longitude).
    blocks = [("b1", 1.5000, 110.3000), ("b2", 1.5000, 110.3050)]
    edges = [("b1", "b2")]

    layout = compute_terrain_layout(blocks, edges)
    x1, y1 = layout["b1"]
    x2, y2 = layout["b2"]

    flow_x, flow_y = x2 - x1, y2 - y1
    angle_from_plus_y = abs(math.atan2(flow_x, flow_y))  # 0 when exactly on +Y
    assert angle_from_plus_y < 1e-6

    # Rotation is an isometry -- real relative distance must be preserved.
    from app.tools.terrain import _flat_earth_projection
    raw = _flat_earth_projection(blocks)
    raw_dist = math.dist(raw["b1"], raw["b2"])
    rotated_dist = math.dist((x1, y1), (x2, y2))
    assert abs(raw_dist - rotated_dist) < 1e-6


def test_multi_block_downhill_chain_preserves_relative_distances():
    """A farm with a real zig-zag (not a straight line) still preserves
    every pairwise distance -- rotation must never distort the layout."""
    blocks = [
        ("b1", 1.5100, 110.3000),
        ("b2", 1.5080, 110.3020),
        ("b3", 1.5050, 110.2990),
    ]
    edges = [("b1", "b2"), ("b2", "b3")]

    from app.tools.terrain import _flat_earth_projection
    raw = _flat_earth_projection(blocks)
    layout = compute_terrain_layout(blocks, edges)

    ids = [b[0] for b in blocks]
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            raw_dist = math.dist(raw[ids[i]], raw[ids[j]])
            rotated_dist = math.dist(layout[ids[i]], layout[ids[j]])
            assert abs(raw_dist - rotated_dist) < 1e-6
