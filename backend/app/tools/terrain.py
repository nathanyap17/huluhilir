"""Terrain canvas rotation/projection. docs/PROJECT_SPEC.md §3 L2 STEP 1-2.

Computed at response time, never persisted (docs/DATA_MODEL.md §5's note on
`blocks.x_rot_m`/`y_rot_m`) -- so a later block or edge edit can't leave a
stale layout behind. This produces the (x_rot_m, y_rot_m) input to the 3D
terrain scene (§9.6); the frontend owns everything past this (z_height,
scene_scale, camera, rendering via @react-three/fiber + expo-gl).

Guardrails this module must never violate (§3 L2, restated in the 3D
context): no absolute lat/lon, no compass rose, no north indicator ever
rendered from this output; rotation is an isometry, so real relative
distances are preserved exactly -- it is a re-orientation, not a distortion.
"""
import math
from statistics import mean

METRES_PER_DEGREE_LAT = 111_320.0


def _flat_earth_projection(
    blocks: list[tuple[str, float, float]]
) -> dict[str, tuple[float, float]]:
    """STEP 1 -- valid at farm scale (~1-3°N in Sarawak). Returns block_id ->
    (x_m, y_m) relative to the centroid of all given blocks."""
    if not blocks:
        return {}
    origin_lat = mean(b[1] for b in blocks)
    origin_lon = mean(b[2] for b in blocks)
    cos_lat = math.cos(math.radians(origin_lat))

    return {
        block_id: (
            (lon - origin_lon) * METRES_PER_DEGREE_LAT * cos_lat,
            (lat - origin_lat) * METRES_PER_DEGREE_LAT,
        )
        for block_id, lat, lon in blocks
    }


def compute_terrain_layout(
    blocks: list[tuple[str, float, float]],
    edges: list[tuple[str, str]],
) -> dict[str, tuple[float, float]]:
    """STEP 1 + STEP 2. `edges` are (from_block_id, to_block_id) pairs,
    upslope -> downslope (flow_edges' own direction, DATA_MODEL.md §6).

    Rotates the whole projected farm so the mean flow direction points along
    +Y ("into the distance" -- EXP-17 in docs/VALIDATION_CHECKLIST.md exists
    to verify this actually holds for a farm not oriented north-south). With
    zero edges (a single-block farm, or before elevation resolution has run)
    there is no flow direction to align to, so rotation is the identity --
    the projection still works, it just isn't guaranteed "hulu at top" yet.
    """
    positions = _flat_earth_projection(blocks)
    if not positions:
        return {}

    edge_vectors = [
        (positions[to_id][0] - positions[from_id][0], positions[to_id][1] - positions[from_id][1])
        for from_id, to_id in edges
        if from_id in positions and to_id in positions
    ]

    if not edge_vectors:
        return positions  # identity rotation -- nothing to align to yet

    mean_dx = mean(v[0] for v in edge_vectors)
    mean_dy = mean(v[1] for v in edge_vectors)
    if mean_dx == 0 and mean_dy == 0:
        return positions

    flow_angle = math.atan2(mean_dy, mean_dx)
    theta = (math.pi / 2) - flow_angle  # rotate flow_vector onto +Y
    cos_t, sin_t = math.cos(theta), math.sin(theta)

    return {
        block_id: (x * cos_t - y * sin_t, x * sin_t + y * cos_t)
        for block_id, (x, y) in positions.items()
    }
