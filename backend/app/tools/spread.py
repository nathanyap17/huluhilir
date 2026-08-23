"""`compute_spread` — deterministic directed-graph disease projection.

docs/PROJECT_SPEC.md §3 L2. NOT machine learning: no labelled transmission-
timing dataset exists. Same inputs must always give the same outputs
(huluhilir-rules skill §7) and the graph is acyclic by construction
(from.elevation_rank < to.elevation_rank), so a plain shortest-path search
never loops.
"""
import heapq

from app.schemas.enums import BlockState, DiseaseClass, ElevationTier
from app.schemas.spread import ComputeSpreadRequest, ComputeSpreadResult, SpreadResultItem

# How much a source diagnosis class drives downhill spread. Healthy/unrelated
# classes seed no projection at all -- there is nothing to spread.
SOURCE_SEVERITY: dict[str, float] = {
    DiseaseClass.collar_lesion.value: 1.0,
    DiseaseClass.defoliation_wilt.value: 0.9,
    DiseaseClass.foliar_yellowing.value: 0.5,
    DiseaseClass.healthy_leaf.value: 0.0,
    DiseaseClass.healthy_collar.value: 0.0,
    DiseaseClass.unrelated.value: 0.0,
    DiseaseClass.unknown.value: 0.0,
}

# Below this, a risk is noise, not a projection -- eta_days stays null
# (docs/DATA_MODEL.md §11: "eta_days ... Null below threshold").
RISK_FLOOR = 0.05

# Baseline days for water/pathogen to traverse one hop under moderate rain,
# before the rain_factor divisor speeds or slows it (docs/PROJECT_SPEC.md §3:
# "foot rot spreads in rain pulses, not continuously").
DAYS_PER_HOP = 2.0

CONFIDENCE_RANGE = {
    ElevationTier.minimal: (0.55, 0.75),
    ElevationTier.optimised: (0.75, 0.95),
}


def _rain_factor(rainfall_7d_mm: float, forecast_7d_mm: float) -> float:
    """Rain pulses drive spread, not steady drizzle. Normalise against a
    100mm/week reference (a genuinely heavy Sarawak week) and cap at 1.0."""
    combined = rainfall_7d_mm + forecast_7d_mm
    return min(1.0, combined / 100.0)


def _confidence(elevation_tier: ElevationTier, farmer_confirmed_fraction: float) -> float:
    lo, hi = CONFIDENCE_RANGE[elevation_tier]
    return round(lo + (hi - lo) * farmer_confirmed_fraction, 3)


def _risk_band(risk: float) -> BlockState:
    if risk >= 0.6:
        return BlockState.harmed
    if risk >= 0.2:
        return BlockState.alerted
    return BlockState.protected


def _shortest_downhill_paths(req: ComputeSpreadRequest) -> dict[str, tuple[list[str], float, float]]:
    """Dijkstra over horizontal_dist_m, restricted to downhill edges
    (from.elevation_rank < to.elevation_rank -- already guaranteed by how the
    graph is built, but re-checked here since this function must never loop
    even if given a malformed graph). Barrier edges (bund/road) are excluded.

    Returns {block_id: (path_block_ids, cumulative_flow_weight, farmer_confirmed_fraction)}
    for every block reachable downhill from the source.
    """
    nodes_by_id = {n.block_id: n for n in req.farm_graph.nodes}
    adjacency: dict[str, list] = {n.block_id: [] for n in req.farm_graph.nodes}
    for edge in req.farm_graph.edges:
        if edge.barrier:
            continue
        from_rank = nodes_by_id[edge.from_block_id].elevation_rank
        to_rank = nodes_by_id[edge.to_block_id].elevation_rank
        if from_rank >= to_rank:
            continue  # not downhill -- skip rather than trust the caller
        adjacency[edge.from_block_id].append(edge)

    # dist = physical distance so far, path = block_ids, cum_w = product of flow_weight,
    # confirmed = running farmer_confirmed fraction (mean over edges on path)
    best: dict[str, tuple[list[str], float, float]] = {}
    frontier = [(0.0, req.source_block_id, [req.source_block_id], 1.0, [])]
    visited_dist: dict[str, float] = {req.source_block_id: 0.0}

    while frontier:
        dist, block_id, path, cum_w, confirmed_flags = heapq.heappop(frontier)
        if dist > visited_dist.get(block_id, float("inf")):
            continue
        for edge in adjacency.get(block_id, []):
            new_dist = dist + edge.horizontal_dist_m
            if new_dist < visited_dist.get(edge.to_block_id, float("inf")):
                visited_dist[edge.to_block_id] = new_dist
                new_path = path + [edge.to_block_id]
                new_cum_w = cum_w * edge.flow_weight
                new_flags = confirmed_flags + [edge.farmer_confirmed]
                best[edge.to_block_id] = (
                    new_path,
                    new_cum_w,
                    sum(new_flags) / len(new_flags),
                )
                heapq.heappush(frontier, (new_dist, edge.to_block_id, new_path, new_cum_w, new_flags))

    return best


def compute_spread(req: ComputeSpreadRequest) -> ComputeSpreadResult:
    severity = SOURCE_SEVERITY.get(req.source_class, 0.0)
    rain_factor = _rain_factor(req.rainfall_7d_mm, req.forecast_7d_mm)
    paths = _shortest_downhill_paths(req)

    results: list[SpreadResultItem] = []
    for block_id, (path, cumulative_w, confirmed_fraction) in paths.items():
        risk = round(min(1.0, cumulative_w * rain_factor * severity), 4)
        confidence = _confidence(req.elevation_tier, confirmed_fraction)

        eta_days = None
        if risk >= RISK_FLOOR:
            hops = len(path) - 1
            rain_intensity = max(0.2, rain_factor)  # avoid div-by-zero on a dry week
            eta_days = max(1, round(DAYS_PER_HOP * hops / rain_intensity))

        results.append(SpreadResultItem(
            block_id=block_id,
            risk=risk,
            risk_band=_risk_band(risk),
            eta_days=eta_days,
            path=path,
            confidence=confidence,
        ))

    results.sort(key=lambda r: r.risk, reverse=True)
    return ComputeSpreadResult(source_block_id=req.source_block_id, results=results, is_estimate=True)
