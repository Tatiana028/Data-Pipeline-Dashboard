import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import exists, select

from src.db.engine import get_engine
from src.db.tables import weather_hourly
from src.etl.cities import load_cities
from src.etl.extract import fetch_weather
from src.etl.load import (
    finish_run,
    refresh_daily,
    save_raw,
    start_run,
    sync_cities,
    upsert_hourly,
)
from src.etl.transform import OpenMeteoResponse, to_rows

CITIES_FILE = Path("config/cities.yaml")
BACKFILL_DAYS = 30  # первый запуск для города: догружаем историю
OVERLAP_DAYS = 2  # обычный запуск: перекрытие, чтобы закрыть пропуски после простоя

log = logging.getLogger(__name__)


def run_status(cities_ok: int, cities_failed: int) -> str:
    """Итог запуска: все города прошли, часть или ни одного."""
    if cities_failed == 0:
        return "success"
    if cities_ok == 0:
        return "failed"
    return "partial"

def run_once() -> str: 
    engine = get_engine()
    city_list = load_cities(CITIES_FILE)

    with engine.begin() as conn:
        city_ids = sync_cities(conn, city_list)
        run_id = start_run(conn)

    now = datetime.now(timezone.utc)
    cities_ok = cities_failed = rows_total = 0
    errors = []

    for city in city_list:
        city_id = city_ids[city.name]
        try:
            with engine.begin() as conn:
                has_data = conn.execute(
                    select(exists().where(weather_hourly.c.city_id == city_id))
                ).scalar()
            past_days = OVERLAP_DAYS if has_data else BACKFILL_DAYS

            response = fetch_weather(city, past_days)

            # Сырой ответ сохраняем отдельной транзакцией — он останется, даже если разбор упадёт
            with engine.begin() as conn:
                save_raw(conn, city_id, run_id, response.status_code, response.json())

            with engine.begin() as conn:
                rows = to_rows(OpenMeteoResponse(**response.json()), city_id, now)
                rows_total += upsert_hourly(conn, rows)
                if rows:
                    refresh_daily(conn, city_id, since=rows[0]["ts"])

            cities_ok += 1
            log.info("%s: %d rows (past_days=%d)", city.name, len(rows), past_days)
        except Exception as exc:
            cities_failed += 1
            errors.append(f"{city.name}: {exc}")
            log.exception("%s: failed", city.name)

    status = run_status(cities_ok, cities_failed)
    with engine.begin() as conn:
        finish_run(conn, run_id, status, cities_ok, cities_failed, rows_total,
                   "\n".join(errors) or None)
    log.info("run %d finished: %s (%d ok, %d failed)", run_id, status, cities_ok, cities_failed)
    return status


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_once()