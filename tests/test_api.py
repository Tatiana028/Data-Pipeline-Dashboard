from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.api import main as api_main
from src.etl.cities import City
from src.etl.load import finish_run, refresh_daily, start_run, sync_cities, upsert_hourly

TOKYO = City(
    name="Tokyo", country="Japan", latitude=35.68, longitude=139.69, timezone="Asia/Tokyo"
)


def hour_row(day: int, hour: int, temp: float) -> dict:
    return {
        "city_id": 1,
        "ts": datetime(2026, 10, day, hour, tzinfo=timezone.utc),
        "temperature_2m": temp,
        "apparent_temperature": None,
        "relative_humidity_2m": None,
        "precipitation": 0.0,
        "wind_speed_10m": None,
        "surface_pressure": None,
        "weather_code": None,
    }


@pytest.fixture
def client(db, monkeypatch):
    """API на тестовой базе с маленьким набором данных: Токио, 3 часа, 1 запуск ETL."""
    with db.begin() as conn:
        sync_cities(conn, [TOKYO])
        upsert_hourly(conn, [hour_row(27, 0, 10.0), hour_row(27, 1, 11.0), hour_row(27, 2, 12.0)])
        refresh_daily(conn, city_id=1, since=datetime(2026, 10, 27, tzinfo=timezone.utc))
        run_id = start_run(conn)
        finish_run(conn, run_id, "success", 1, 0, 3, None)
    # API создал своё подключение при импорте — направляем его в тестовую базу
    monkeypatch.setattr(api_main, "engine", db)
    return TestClient(api_main.app)


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok"}


def test_latest_has_city_name(client):
    response = client.get("/weather/latest")
    assert response.status_code == 200
    [row] = response.json()
    assert row["city_name"] == "Tokyo"
    assert row["temperature_2m"] == 12.0  # самый свежий из трёх часов


def test_hourly_for_period(client):
    params = {"city_id": 1, "date_from": "2026-10-27", "date_to": "2026-10-27"}
    response = client.get("/weather/hourly", params=params)
    assert response.status_code == 200
    assert [row["temperature_2m"] for row in response.json()] == [10.0, 11.0, 12.0]


def test_daily_for_period(client):
    params = {"city_id": 1, "date_from": "2026-10-27", "date_to": "2026-10-27"}
    response = client.get("/weather/daily", params=params)
    assert response.status_code == 200
    [day] = response.json()
    assert day["temp_max"] == 12.0
    assert day["hours_count"] == 3


def test_error_codes(client):
    assert client.get("/weather/hourly", params={"city_id": 99}).status_code == 404
    assert client.get("/weather/hourly", params={"city_id": "abc"}).status_code == 422
    bad_period = {"city_id": 1, "date_from": "2026-10-28", "date_to": "2026-10-20"}
    assert client.get("/weather/daily", params=bad_period).status_code == 422


def test_etl_runs(client):
    response = client.get("/etl/runs")
    assert response.status_code == 200
    assert response.json()[0]["status"] == "success"