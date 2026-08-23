"""find_spray_window arithmetic — the rainfast-vs-forecast core of the demo arbitration."""
from app.schemas.treatment import FindSprayWindowRequest, ForecastPoint
from app.tools.treatment import find_spray_window


def test_no_rainfast_hours_is_always_immediately_viable():
    """Biological/cultural treatments (e.g. Trichoderma, drainage) have no
    rainfast window -- nothing to wash off."""
    req = FindSprayWindowRequest(treatment_id="trichoderma_biocontrol", rainfast_hours=None, forecast=[])
    result = find_spray_window(req)
    assert result.defer_cause is None
    assert result.recommended_window is not None
    assert result.recommended_window.rain_free is True


def test_rain_inside_rainfast_window_defers():
    """L3: 24h rain-fast · Weather: 46mm tomorrow -> the core arbitration
    moment (docs/PROJECT_SPEC.md §3 L4)."""
    req = FindSprayWindowRequest(
        treatment_id="metalaxyl_drench",
        rainfast_hours=24,
        forecast=[
            ForecastPoint(date="2026-08-23T06:00:00", rainfall_mm=0, probability=0.1),
            # rain falls 12h after this start -- strictly inside the 24h rainfast window
            ForecastPoint(date="2026-08-23T18:00:00", rainfall_mm=46, probability=0.8),
        ],
    )
    result = find_spray_window(req)
    assert result.defer_cause == "rainfast"
    assert result.recommended_window is None


def test_dry_window_is_recommended():
    req = FindSprayWindowRequest(
        treatment_id="metalaxyl_drench",
        rainfast_hours=24,
        forecast=[
            ForecastPoint(date="2026-08-23T06:00:00", rainfall_mm=0, probability=0.1),
            ForecastPoint(date="2026-08-24T06:00:00", rainfall_mm=0, probability=0.1),
            ForecastPoint(date="2026-08-25T06:00:00", rainfall_mm=46, probability=0.8),
        ],
    )
    result = find_spray_window(req)
    assert result.defer_cause is None
    assert result.recommended_window is not None
    assert result.recommended_window.window_start.isoformat().startswith("2026-08-23")
