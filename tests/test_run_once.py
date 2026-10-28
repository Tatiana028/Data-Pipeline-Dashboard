import json
from pathlib import Path

import httpx
from sqlalchemy import func, select

from src.db.tables import etl_runs, raw_responses, weather_hourly
from src.etl import run_once as run_module

PROJECT_ROOT = Path(__file__).parent.parent
FIXTURE = Path(__file__).parent / "fixtures" / "open_meteo_berlin.json"


def test_run_status():
    assert run_module.run_status(cities_ok=6, cities_failed=0) == "success"
    assert run_module.run_status(cities_ok=5, cities_failed=1) == "partial"
    assert run_module.run_status(cities_ok=0, cities_failed=6) == "failed"


def test_one_failing_city_does_not_stop_others(db, monkeypatch):
    payload = json.loads(FIXTURE.read_text())
 
    def fake_fetch(city, past_days):
        if city.name == "Tokyo":
            raise httpx.ConnectError("connection refused")
        return httpx.Response(200, json=payload)

    monkeypatch.setattr(run_module, "fetch_weather", fake_fetch)
    monkeypatch.chdir(PROJECT_ROOT)  # run_once читает config/cities.yaml по относительному пути

    status = run_module.run_once()

    with db.begin() as conn:
        run = conn.execute(select(etl_runs)).one()
        hourly_rows = conn.execute(select(func.count()).select_from(weather_hourly)).scalar()
        raw_rows = conn.execute(select(func.count()).select_from(raw_responses)).scalar()

    assert status == "partial"
    assert run.status == "partial"
    assert run.finished_at is not None
    assert (run.cities_ok, run.cities_failed) == (5, 1)
    assert "Tokyo" in run.error
    assert hourly_rows == 5 * 3
    assert raw_rows == 5
