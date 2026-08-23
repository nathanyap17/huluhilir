"""Farm graph derivation. docs/PROJECT_SPEC.md §5.

Turns a completed walk (block positions + either farmer water-direction
answers or barometer readings) into `elevation_rank`s and the acyclic
`flow_edges` set that L2's compute_spread traverses.

huluhilir-rules skill §3 is enforced structurally here: the farmer's answer
ALWAYS wins over any sensor, and every disagreement is written to
`elevation_conflicts` with `resolution="farmer"` rather than silently
resolved. Nothing in this module can auto-override a farmer.
"""
import math
from statistics import median
from typing import Iterable, Optional

from app.models.core import Block, ElevationConflict, FlowEdge

# Sensor gate: below this the barometer cannot be trusted to separate two
# blocks, so the farmer is asked instead (docs/PROJECT_SPEC.md §4 / §5 ③).
# EXP-4 was meant to calibrate this against real device drift but is still
# BLOCKED on having a physical barometer phone -- 2.0 m is the spec's
# documented default, not a measured value.
DELTA_H_GATE_M = 2.0

K_NEAREST = 3

# flow_weight = w1*norm(slope) + w2*(1/dist) + w3*drainage(j)
# (docs/PROJECT_SPEC.md §5 ④). The three weights are a judgment call -- no
# calibration dataset exists (that's the L2 roadmap item), so they are
# deliberately simple and equal-ish rather than falsely precise.
W_SLOPE, W_PROXIMITY, W_DRAINAGE = 0.4, 0.3, 0.3

# Poor drainage pools water at the receiving block -> higher arrival risk.
_DRAINAGE_FACTOR = {"good": 0.2, "fair": 0.5, "poor": 1.0}


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def median_centroid(points: Iterable[tuple[float, float]]) -> tuple[float, float]:
    """Median, not mean -- rejects GPS jitter spikes during the ±5 s capture
    window (docs/PROJECT_SPEC.md §5 ①). EXP-6 (GPS accuracy under canopy) is
    still blocked on a real phone, so jitter magnitude is unmeasured."""
    pts = list(points)
    if not pts:
        raise ValueError("no position samples to derive a centroid from")
    return median(p[0] for p in pts), median(p[1] for p in pts)


def resolve_elevation_ranks(
    block_ids: list[str],
    farmer_pairs: dict[tuple[str, str], str],
    baro_rel_by_block: Optional[dict[str, float]] = None,
) -> tuple[dict[str, int], list[dict]]:
    """Derive a total elevation ordering (1 = highest, unique per farm).

    farmer_pairs maps (block_a, block_b) -> 'a_higher' | 'b_higher'. These are
    authoritative. baro_rel_by_block is the OPTIMISED-tier sensor input and is
    only consulted for pairs the farmer was not asked about.

    Returns (ranks, conflicts) where conflicts are dicts ready to become
    ElevationConflict rows -- always resolution='farmer'.
    """
    conflicts: list[dict] = []

    # Count how many other blocks each block is above; more wins => higher.
    # A simple ordering score rather than a topological sort: the farmer's
    # answers may be intransitive (a>b, b>c, c>a is entirely possible from a
    # real person), and a scoring approach degrades gracefully where a strict
    # sort would raise. Ties broken by baro_rel, then block_id, so the result
    # is deterministic and elevation_rank stays unique per farm.
    above_count: dict[str, int] = {b: 0 for b in block_ids}

    for (block_a, block_b), answer in farmer_pairs.items():
        higher = block_a if answer == "a_higher" else block_b
        lower = block_b if answer == "a_higher" else block_a
        if higher in above_count:
            above_count[higher] += 1

        if baro_rel_by_block and block_a in baro_rel_by_block and block_b in baro_rel_by_block:
            delta_h = baro_rel_by_block[block_a] - baro_rel_by_block[block_b]
            baro_says = "a_higher" if delta_h > 0 else "b_higher"
            if baro_says != answer:
                conflicts.append({
                    "block_a_id": block_a,
                    "block_b_id": block_b,
                    "farmer_says": answer,
                    "barometer_says": baro_says,
                    "resolution": "farmer",  # ALWAYS -- huluhilir-rules §3
                    "delta_h_m": abs(delta_h),
                })

    def sort_key(block_id: str):
        return (
            -above_count.get(block_id, 0),
            -(baro_rel_by_block or {}).get(block_id, 0.0),
            block_id,
        )

    ordered = sorted(block_ids, key=sort_key)
    ranks = {block_id: i + 1 for i, block_id in enumerate(ordered)}
    return ranks, conflicts


def pairs_needing_farmer_input(
    block_ids: list[str], baro_rel_by_block: Optional[dict[str, float]]
) -> list[tuple[str, str]]:
    """Which adjacent pairs must the farmer be asked about?

    MINIMAL (no barometer): all adjacent pairs, n-1 questions.
    OPTIMISED: only pairs the sensor cannot separate (Δh < 2.0 m).
    docs/PROJECT_SPEC.md §4.
    """
    if not baro_rel_by_block:
        return [(block_ids[i], block_ids[i + 1]) for i in range(len(block_ids) - 1)]

    by_height = sorted(block_ids, key=lambda b: -baro_rel_by_block.get(b, 0.0))
    ambiguous = []
    for i in range(len(by_height) - 1):
        a, b = by_height[i], by_height[i + 1]
        if abs(baro_rel_by_block.get(a, 0.0) - baro_rel_by_block.get(b, 0.0)) < DELTA_H_GATE_M:
            ambiguous.append((a, b))
    return ambiguous


def build_flow_edges(farm_id: str, blocks: list[Block], source: str = "farmer") -> list[FlowEdge]:
    """k-NN (k=3) candidate edges, kept only where rank_from < rank_to.

    Acyclic by construction -- an edge can only ever run from a
    higher-ranked (more upslope) block to a lower-ranked one, so
    compute_spread's traversal cannot loop (docs/DATA_MODEL.md §6).
    """
    edges: list[FlowEdge] = []
    for i, from_block in enumerate(blocks):
        neighbours = sorted(
            (
                (haversine_m(from_block.centroid_lat, from_block.centroid_lon, other.centroid_lat, other.centroid_lon), other)
                for j, other in enumerate(blocks)
                if j != i
            ),
            key=lambda pair: pair[0],
        )[:K_NEAREST]

        for dist_m, to_block in neighbours:
            if from_block.elevation_rank >= to_block.elevation_rank:
                continue  # not downhill -- skip, keeps the graph acyclic

            elevation_drop_m = None
            slope_ratio = None
            if from_block.baro_rel_m is not None and to_block.baro_rel_m is not None:
                elevation_drop_m = from_block.baro_rel_m - to_block.baro_rel_m
                slope_ratio = elevation_drop_m / dist_m if dist_m > 0 else None

            # norm(slope): 0.1 (1:10) is already a strong slope for pepper terrain
            norm_slope = min(1.0, abs(slope_ratio) / 0.1) if slope_ratio is not None else 0.5
            proximity = 1.0 / (1.0 + dist_m / 50.0)
            drainage_factor = _DRAINAGE_FACTOR.get(to_block.drainage, 0.5)

            flow_weight = round(
                min(1.0, W_SLOPE * norm_slope + W_PROXIMITY * proximity + W_DRAINAGE * drainage_factor), 3
            )

            edges.append(FlowEdge(
                farm_id=farm_id,
                from_block_id=from_block.block_id,
                to_block_id=to_block.block_id,
                horizontal_dist_m=round(dist_m, 1),
                elevation_drop_m=elevation_drop_m,
                slope_ratio=slope_ratio,
                flow_weight=flow_weight,
                source=source,
                farmer_confirmed=(source == "farmer"),
            ))
    return edges
