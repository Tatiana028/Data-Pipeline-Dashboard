from datetime import date, datetime, time, timedelta, timezone

from fastapi import FastAPI, HTTPException, Query
from sqlalchemy import Connection, select, text
from sqlalchemy.dialects.postgresql import distinct_on

from src.api.schemas import CityOut, DailyOut, HourlyOut, LatestOut, RunOut
from src.db.engine import get_engine
from src.db.tables import cities, etl_runs, weather_daily, weather_hourly

app = FastAPI(title="Weather Data API")
engine = get_engine()


def ensure_city_exists(conn: Connection, city_id: int) -> None:
    """404, если такого города нет."""
    found = conn.execute(select(cities.c.id).where(cities.c.id == city_id)).first()
    if found is None:
        raise HTTPException(status_code=404, detail=f"city {city_id} not found")


def resolve_period(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    """Период по умолчанию — последние 7 дней; date_from не может быть позже date_to."""
    date_to = date_to or datetime.now(timezone.utc).date()
    date_from = date_from or date_to - timedelta(days=6)
    if date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must not be after date_to")
    return date_from, date_to


@app.get("/health")
def health() -> dict: 
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=503, detail="database unavailable")
    return {"status": "ok", "db": "ok"}

@app.get("/cities", response_model=list[CityOut])
def list_cities() -> list[dict]:
    """Все города, по которым собираем погоду."""
    with engine.connect() as conn:
        rows = conn.execute(select(cities).order_by(cities.c.name)).mappings().all()
    return rows

@app.get("/weather/latest", response_model=list[LatestOut])
def latest_weather() -> list[dict]:
    """Последний записанный час по каждому городу."""
    h = weather_hourly.c
    query = (
        select(weather_hourly, cities.c.name.label("city_name"))
        .join(cities, cities.c.id == h.city_id)
        .ext(distinct_on(h.city_id))
        .order_by(h.city_id, h.ts.desc())
    )
    with engine.connect() as conn:
        return conn.execute(query).mappings().all()


@app.get("/weather/hourly", response_model=list[HourlyOut])
def hourly_weather(
    city_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(1000, ge=1, le=5000),
    offset: int = Query(0, ge=0),
) -> list[dict]:
    """Почасовая погода города за период (даты по UTC), от старых часов к новым."""
    date_from, date_to = resolve_period(date_from, date_to)
    start = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc)
    h = weather_hourly.c
    query = (
        select(weather_hourly)
        .where(h.city_id == city_id, h.ts >= start, h.ts < end)
        .order_by(h.ts)
        .limit(limit)
        .offset(offset)
    )
    with engine.connect() as conn:
        ensure_city_exists(conn, city_id)
        return conn.execute(query).mappings().all()


@app.get("/weather/daily", response_model=list[DailyOut])
def daily_weather(
    city_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict]:
    """Дневные итоги города за период (даты по местному времени города)."""
    date_from, date_to = resolve_period(date_from, date_to)
    d = weather_daily.c
    query = (
        select(weather_daily)
        .where(d.city_id == city_id, d.date >= date_from, d.date <= date_to)
        .order_by(d.date)
    )
    with engine.connect() as conn:
        ensure_city_exists(conn, city_id)
        return conn.execute(query).mappings().all()


@app.get("/etl/runs", response_model=list[RunOut])
def etl_run_log(limit: int = Query(50, ge=1, le=500)) -> list[dict]:
    """Последние запуски ETL, новые сверху."""
    query = select(etl_runs).order_by(etl_runs.c.started_at.desc()).limit(limit)
    with engine.connect() as conn:
        return conn.execute(query).mappings().all()
