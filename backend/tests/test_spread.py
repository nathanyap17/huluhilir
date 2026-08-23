"""PLAN.md Block B: 'Unit tests | Graph acyclicity, edge weights, ETA monotonicity'."""
from app.schemas.enums import DiseaseClass, ElevationTier
from app.schemas.spread import ComputeSpreadRequest, FarmGraph, FarmGraphEdge, FarmGraphNode
from app.tools.spread import compute_spread


def _linear_graph(cyclic_edge: bool = False) -> FarmGraph:
    """blk1 (rank 1, highest) -> blk2 (rank 2) -> blk3 (rank 3, lowest)."""
    nodes = [
        FarmGraphNode(block_id="blk1", elevation_rank=1),
        FarmGraphNode(block_id="blk2", elevation_rank=2),
        FarmGraphNode(block_id="blk3", elevation_rank=3),
    ]
    edges = [
        FarmGraphEdge(from_block_id="blk1", to_block_id="blk2", horizontal_dist_m=50, flow_weight=0.8),
        FarmGraphEdge(from_block_id="blk2", to_block_id="blk3", horizontal_dist_m=50, flow_weight=0.8),
    ]
    if cyclic_edge:
        # blk3 -> blk1 goes uphill (rank 3 -> rank 1); must be excluded, not looped on.
        edges.append(FarmGraphEdge(from_block_id="blk3", to_block_id="blk1", horizontal_dist_m=50, flow_weight=0.9))
    return FarmGraph(nodes=nodes, edges=edges)


def _request(rainfall_7d_mm: float, forecast_7d_mm: float, cyclic_edge: bool = False) -> ComputeSpreadRequest:
    return ComputeSpreadRequest(
        source_block_id="blk1",
        source_class=DiseaseClass.collar_lesion.value,
        farm_graph=_linear_graph(cyclic_edge),
        rainfall_7d_mm=rainfall_7d_mm,
        forecast_7d_mm=forecast_7d_mm,
        elevation_tier=ElevationTier.minimal,
    )


def test_reaches_all_downhill_blocks():
    result = compute_spread(_request(rainfall_7d_mm=40, forecast_7d_mm=40))
    reached = {r.block_id for r in result.results}
    assert reached == {"blk2", "blk3"}


def test_acyclic_uphill_edge_never_loops_and_is_excluded():
    """An uphill edge (blk3 -> blk1) must be ignored, not followed -- and must
    not cause compute_spread to hang or raise."""
    result = compute_spread(_request(rainfall_7d_mm=40, forecast_7d_mm=40, cyclic_edge=True))
    reached = {r.block_id for r in result.results}
    assert reached == {"blk2", "blk3"}
    for r in result.results:
        assert "blk1" not in r.path[1:]  # source may only appear once, at index 0


def test_risk_and_confidence_are_bounded():
    result = compute_spread(_request(rainfall_7d_mm=100, forecast_7d_mm=100))
    for r in result.results:
        assert 0.0 <= r.risk <= 1.0
        assert 0.55 <= r.confidence <= 0.75  # minimal tier range, docs/PROJECT_SPEC.md §4
        assert r.is_estimate is True if hasattr(r, "is_estimate") else True
    assert result.is_estimate is True


def test_farther_block_has_lower_or_equal_risk():
    result = compute_spread(_request(rainfall_7d_mm=60, forecast_7d_mm=60))
    by_block = {r.block_id: r.risk for r in result.results}
    assert by_block["blk3"] <= by_block["blk2"]  # two hops of decay vs one


def test_eta_monotonic_with_rainfall_heavier_rain_arrives_sooner():
    dry = compute_spread(_request(rainfall_7d_mm=5, forecast_7d_mm=5))
    wet = compute_spread(_request(rainfall_7d_mm=90, forecast_7d_mm=90))

    dry_eta = {r.block_id: r.eta_days for r in dry.results if r.eta_days is not None}
    wet_eta = {r.block_id: r.eta_days for r in wet.results if r.eta_days is not None}

    for block_id in wet_eta:
        if block_id in dry_eta:
            assert wet_eta[block_id] <= dry_eta[block_id]


def test_no_source_class_severity_gives_zero_risk():
    req = _request(rainfall_7d_mm=80, forecast_7d_mm=80)
    req = req.model_copy(update={"source_class": DiseaseClass.healthy_leaf.value})
    result = compute_spread(req)
    assert all(r.risk == 0.0 for r in result.results)
    assert all(r.eta_days is None for r in result.results)
