from datetime import datetime, timezone

from sqlalchemy import select

from src.db.tables import weather_daily, weather_hourly
from src.etl.cities import City
from src.etl.load import refresh_daily, sync_cities, upsert_hourly

TOKYO = City(
    name="Tokyo", country="Japan", latitude=35.68, longitude=139.69, timezone="Asia/Tokyo"
)


def hour_row(day: int, hour: int, temp: float) -> dict:
    """Одна почасовая строка для города с id=1; остальные метрики не важны."""
    return {
        "city_id": 1,
        "ts": datetime(2026, 10, day, hour, tzinfo=timezone.utc),
        "temperature_2m": temp,
        "apparent_temperature": None,
        "relative_humidity_2m": None,
        "precipitation": 0.5,
        "wind_speed_10m": None,
        "surface_pressure": None,
        "weather_code": None,
    }


def test_upsert_twice_updates_instead_of_duplicating(db):
    with db.begin() as conn:
        sync_cities(conn, [TOKYO])
        upsert_hourly(conn, [hour_row(27, 0, 10.0), hour_row(27, 1, 11.0)])
        # Второй запуск за те же часы, значение за 01:00 уточнилось
        upsert_hourly(conn, [hour_row(27, 0, 10.0), hour_row(27, 1, 12.5)])

        temps = conn.execute(
            select(weather_hourly.c.temperature_2m).order_by(weather_hourly.c.ts)
        ).scalars().all()

    assert temps == [10.0, 12.5]


def test_daily_aggregates_use_local_date(db):
    # Полночь в Токио = 15:00 UTC: 14:00 UTC ещё 26-е, а 15:00 и 16:00 UTC — уже 27-е
    with db.begin() as conn:
        sync_cities(conn, [TOKYO])
        upsert_hourly(conn, [hour_row(26, 14, 5.0), hour_row(26, 15, 20.0), hour_row(26, 16, 22.0)])
        refresh_daily(conn, city_id=1, since=datetime(2026, 10, 26, tzinfo=timezone.utc))

        days = conn.execute(
            select(weather_daily.c.date, weather_daily.c.temp_max, weather_daily.c.hours_count)
            .order_by(weather_daily.c.date)
        ).all()

    assert [(str(d), t, n) for d, t, n in days] == [
        ("2026-10-26", 5.0, 1),
        ("2026-10-27", 22.0, 2),
    ]
