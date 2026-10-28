from datetime import date, datetime

from pydantic import BaseModel


class CityOut(BaseModel):
    """Город в ответе API."""

    id: int
    name: str
    country: str
    latitude: float
    longitude: float
    timezone: str

class HourlyOut(BaseModel):
    """Один час погоды по одному городу."""

    city_id: int
    ts: datetime
    temperature_2m: float | None
    apparent_temperature: float | None
    relative_humidity_2m: float | None
    precipitation: float | None
    wind_speed_10m: float | None
    surface_pressure: float | None
    weather_code: int | None


class LatestOut(HourlyOut):

    city_name: str


class DailyOut(BaseModel):
    """Итоги одного дня по одному городу (дата — по местному времени города)."""

    city_id: int
    date: date
    temp_min: float | None
    temp_max: float | None
    temp_avg: float | None
    precipitation_sum: float | None
    wind_speed_max: float | None
    humidity_avg: float | None
    hours_count: int


class RunOut(BaseModel):
    """Один запуск ETL из журнала etl_runs."""

    id: int
    started_at: datetime
    finished_at: datetime | None
    status: str
    cities_ok: int
    cities_failed: int
    rows_upserted: int
    error: str | None