"""weather_observations, weather_forecasts. docs/DATA_MODEL.md §22."""
from sqlalchemy import Boolean, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WeatherObservation(Base):
    __tablename__ = "weather_observations"

    station_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    observed_date: Mapped[str] = mapped_column(String(10), primary_key=True)
    rainfall_mm: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(30))
    is_cached_fallback: Mapped[bool] = mapped_column(Boolean, default=False)


class WeatherForecast(Base):
    __tablename__ = "weather_forecasts"

    station_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    forecast_date: Mapped[str] = mapped_column(String(10), primary_key=True)
    issued_at: Mapped[str] = mapped_column(String(30), primary_key=True)
    rainfall_mm: Mapped[float] = mapped_column(Float)
    probability: Mapped[float] = mapped_column(Float)
