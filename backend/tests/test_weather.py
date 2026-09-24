"""get_weather -- cached-fallback date re-anchoring.

The cached fallback (seed/weather_cache_kuching.json) is a one-time static
snapshot. Without re-anchoring, its dates eventually all land in the past
relative to the real "today", and forecast_7d silently comes back empty
forever after -- this is what broke the live arbitration test
(docs/VALIDATION_CHECKLIST.md EXP-9 log entry, 2026-09-18). Not a window-
size bug, not a provider bug: a frozen-snapshot bug.
"""
from datetime import date, timedelta

from app.tools.weather import _reanchor_dates_to_today, _rows_from_data_gov_my_payload

STATION_ID = "Tn187"


def _synthetic_cached_payload(anchor_date: date) -> dict:
    """7 rows spanning [anchor-3, anchor+3], mirroring the real cache's
    shape and station_id -- but with a caller-controlled anchor so the test
    doesn't depend on the wall clock ever catching up to a real snapshot."""
    return {
        "value": [
            {
                "location": {"location_id": STATION_ID, "location_name": "Kuching"},
                "date": (anchor_date + timedelta(days=offset)).isoformat(),
                "summary_forecast": "Tiada Hujan",
            }
            for offset in range(-3, 4)
        ]
    }


def test_reanchor_centers_the_cached_window_on_today():
    old_anchor = date.today() - timedelta(days=365)  # simulate a long-stale cache
    payload = _synthetic_cached_payload(old_anchor)["value"]

    reanchored = _reanchor_dates_to_today(payload)
    reanchored_dates = sorted(r["date"] for r in reanchored)

    expected = sorted((date.today() + timedelta(days=d)).isoformat() for d in range(-3, 4))
    assert reanchored_dates == expected


def test_reanchor_is_a_noop_on_empty_rows():
    assert _reanchor_dates_to_today([]) == []


def test_cached_fallback_still_populates_forecast_7d_after_a_year_of_staleness():
    """The actual bug: a cache this old used to leave forecast_7d empty."""
    old_anchor = date.today() - timedelta(days=365)
    payload = _synthetic_cached_payload(old_anchor)

    result = _rows_from_data_gov_my_payload(payload, STATION_ID, is_cached_fallback=True)

    assert result.forecast_7d, "forecast_7d is empty -- the stale-cache bug regressed"
    assert result.rainfall_7d, "rainfall_7d is empty -- re-anchoring broke the past-day bucket"
    # 3 days before today + today itself = 4 observations; 3 days after = 3 forecasts.
    assert len(result.rainfall_7d) == 4
    assert len(result.forecast_7d) == 3


def test_live_payload_dates_are_never_reanchored():
    """Live data is already correctly aligned to the real world -- shifting
    it would be actively wrong, not just unnecessary."""
    today = date.today()
    payload = [
        {
            "location": {"location_id": STATION_ID, "location_name": "Kuching"},
            "date": (today + timedelta(days=2)).isoformat(),
            "summary_forecast": "Hujan",
        }
    ]
    result = _rows_from_data_gov_my_payload(payload, STATION_ID, is_cached_fallback=False)
    assert result.forecast_7d[0].forecast_date == (today + timedelta(days=2)).isoformat()
