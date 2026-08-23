"""`get_weather` tool contract. docs/DATA_MODEL.md §22. Cached fallback is demo insurance."""
from pydantic import Field

from app.schemas.common import ORMModel
from app.schemas.enums import WeatherSource


class WeatherObservationOut(ORMModel):
    station_id: str
    observed_date: str
    rainfall_mm: float
    source: WeatherSource
    is_cached_fallback: bool = Field(description="True when API unavailable")


class WeatherForecastOut(ORMModel):
    station_id: str
    forecast_date: str
    issued_at: str
    rainfall_mm: float
    probability: float


class GetWeatherRequest(ORMModel):
    farm_id: str


class GetWeatherResult(ORMModel):
    station_id: str
    rainfall_7d: list[WeatherObservationOut]
    forecast_7d: list[WeatherForecastOut]
    is_cached_fallback: bool
