 
from sqlalchemy.dialects.postgresql import insert

from src.db.tables import cities, etl_runs, raw_responses, weather_daily, weather_hourly
from src.etl.cities import City
from src.etl.extract import HOURLY_METRICS

from datetime import datetime

from sqlalchemy import Connection, func, select


def sync_cities(conn: Connection, city_list: list[City]) -> dict[str, int]: 
    stmt = insert(cities).values([c.model_dump() for c in city_list])
    stmt = stmt.on_conflict_do_update(
        index_elements=["name", "country"],
        set_={
            "latitude": stmt.excluded.latitude,
            "longitude": stmt.excluded.longitude,
            "timezone": stmt.excluded.timezone,
        },
    ).returning(cities.c.id, cities.c.name)
    return {name: city_id for city_id, name in conn.execute(stmt)}

def upsert_hourly(conn: Connection, rows: list[dict]) -> int: 
    if not rows:
        return 0
    stmt = insert(weather_hourly).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["city_id", "ts"],
        set_={
            **{m: stmt.excluded[m] for m in HOURLY_METRICS},
            "ingested_at": func.now(),
        },
    )
    conn.execute(stmt)
    return len(rows)

def start_run(conn: Connection) -> int: 
    return conn.execute(insert(etl_runs).returning(etl_runs.c.id)).scalar_one()


def finish_run(conn: Connection, run_id: int, status: str, cities_ok: int,
               cities_failed: int, rows_upserted: int, error: str | None) -> None: 
    conn.execute(
        etl_runs.update()
        .where(etl_runs.c.id == run_id)
        .values(
            finished_at=func.now(),
            status=status,
            cities_ok=cities_ok,
            cities_failed=cities_failed,
            rows_upserted=rows_upserted,
            error=error,
        )
    )


def save_raw(conn: Connection, city_id: int, run_id: int, http_status: int,
             payload: dict) -> None: 
    conn.execute(
        insert(raw_responses).values(
            city_id=city_id, run_id=run_id, http_status=http_status, payload=payload
        )
    )

def refresh_daily(conn: Connection, city_id: int, since: datetime) -> None: 
    h = weather_hourly.c
    # Дата по местному времени города, а не по UTC
    local_date = func.date(func.timezone(cities.c.timezone, h.ts))
    since_local = func.date(func.timezone(cities.c.timezone, since))

    agg = (
        select(
            h.city_id,
            local_date,
            func.min(h.temperature_2m),
            func.max(h.temperature_2m),
            func.avg(h.temperature_2m),
            func.sum(h.precipitation),
            func.max(h.wind_speed_10m),
            func.avg(h.relative_humidity_2m),
            func.count(),
        )
        .join(cities, cities.c.id == h.city_id)
        .where(h.city_id == city_id, local_date >= since_local)
        .group_by(h.city_id, local_date)
    )

    stmt = insert(weather_daily).from_select(
        ["city_id", "date", "temp_min", "temp_max", "temp_avg", "precipitation_sum",
         "wind_speed_max", "humidity_avg", "hours_count"],
        agg,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["city_id", "date"],
        set_={
            "temp_min": stmt.excluded.temp_min,
            "temp_max": stmt.excluded.temp_max,
            "temp_avg": stmt.excluded.temp_avg,
            "precipitation_sum": stmt.excluded.precipitation_sum,
            "wind_speed_max": stmt.excluded.wind_speed_max,
            "humidity_avg": stmt.excluded.humidity_avg,
            "hours_count": stmt.excluded.hours_count,
            "updated_at": func.now(),
        },
    )
    conn.execute(stmt)