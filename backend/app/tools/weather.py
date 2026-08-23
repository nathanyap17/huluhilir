"""`get_weather` — data.gov.my forecast, cached fallback. docs/PROJECT_SPEC.md §3 L2 input.

EXP-9 (sandbox/EXPERIMENTS.md) found: data.gov.my's forecast API works;
DID Sarawak's CKAN rainfall-gauge API does not resolve from this network.
There is therefore no live *observed* rainfall feed -- both "last 7 days"
and "next 7 days" are derived from the same qualitative forecast text,
mapped to an mm estimate. This is honestly weaker than a real rain gauge;
`is_cached_fallback` is set whenever the live API call fails so the UI and
logs can say so.
"""
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx

from app.config import settings
from app.schemas.weather import GetWeatherResult, WeatherForecastOut, WeatherObservationOut

CACHE_PATH = Path(__file__).parent.parent.parent / "seed" / "weather_cache_kuching.json"
DATA_GOV_MY_URL = "https://api.data.gov.my/weather/forecast"
DEFAULT_LOCATION = "Kuching"

# Ordered most-severe-first: first substring match wins. Malaysian met-service
# forecast text is qualitative, not numeric -- these mm/probability values are
# a documented estimation heuristic, not a measurement.
_SEVERITY_KEYWORDS: list[tuple[str, float, float]] = [
    ("hujan lebat", 40.0, 0.80),
    ("ribut petir di kebanyakan tempat", 25.0, 0.65),
    ("ribut petir di beberapa tempat", 15.0, 0.50),
    ("ribut petir", 20.0, 0.55),
    ("hujan", 8.0, 0.60),
    ("jerebu", 0.0, 0.02),
    ("tiada hujan", 0.0, 0.05),
]


def estimate_rainfall_mm(forecast_text: str) -> tuple[float, float]:
    text = forecast_text.lower()
    for keyword, mm, probability in _SEVERITY_KEYWORDS:
        if keyword in text:
            return mm, probability
    return 0.0, 0.05  # unrecognised text -> assume dry rather than over-warn


def _rows_from_data_gov_my_payload(payload, station_id: str, is_cached_fallback: bool) -> GetWeatherResult:
    """The live API returns a bare JSON list; the PowerShell-captured cache
    asset (sandbox/cached_weather_kuching.json, EXP-9) wraps it as
    {"value": [...], "Count": N} -- accept either shape."""
    today = datetime.now().date()
    issued_at = datetime.now().isoformat()

    observations: list[WeatherObservationOut] = []
    forecasts: list[WeatherForecastOut] = []

    all_rows = payload if isinstance(payload, list) else payload.get("value", [])
    rows = [r for r in all_rows if r["location"]["location_id"] == station_id]
    for row in rows:
        row_date = date.fromisoformat(row["date"])
        mm, probability = estimate_rainfall_mm(row.get("summary_forecast", row.get("afternoon_forecast", "")))
        if row_date <= today:
            observations.append(WeatherObservationOut(
                station_id=station_id,
                observed_date=row["date"],
                rainfall_mm=mm,
                source="data_gov_my",
                is_cached_fallback=is_cached_fallback,
            ))
        else:
            forecasts.append(WeatherForecastOut(
                station_id=station_id,
                forecast_date=row["date"],
                issued_at=issued_at,
                rainfall_mm=mm,
                probability=probability,
            ))

    # Keep a 7-day window each side of today, newest first for observations.
    observations = sorted(observations, key=lambda o: o.observed_date, reverse=True)[:7]
    forecasts = sorted(forecasts, key=lambda f: f.forecast_date)[:7]

    return GetWeatherResult(
        station_id=station_id,
        rainfall_7d=observations,
        forecast_7d=forecasts,
        is_cached_fallback=is_cached_fallback,
    )


def get_weather(farm_id: str, station_id: str = "Tn187") -> GetWeatherResult:
    """farm_id is accepted for the tool signature (per docs/PROJECT_SPEC.md
    §3 L4 tool list) but this MVP does not yet resolve farm -> station beyond
    the single demo station; see Block D for real farm.weather_station_id wiring.
    """
    try:
        resp = httpx.get(
            DATA_GOV_MY_URL,
            params={"contains": f"{DEFAULT_LOCATION}@location__location_name"},
            timeout=5.0,
            follow_redirects=True,
        )
        resp.raise_for_status()
        return _rows_from_data_gov_my_payload(resp.json(), station_id, is_cached_fallback=False)
    except (httpx.HTTPError, ValueError, KeyError):
        # utf-8-sig: PowerShell (WORKSPACE_SETUP prep) wrote this file with a BOM
        cached = json.loads(CACHE_PATH.read_text(encoding="utf-8-sig"))
        return _rows_from_data_gov_my_payload(cached, station_id, is_cached_fallback=True)
