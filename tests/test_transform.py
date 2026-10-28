import json
from datetime import datetime, timezone
from pathlib import Path
import pytest

from src.etl.transform import OpenMeteoResponse, to_rows

FIXTURE = Path(__file__).parent / "fixtures" / "open_meteo_berlin.json"


def load_fixture() -> OpenMeteoResponse: 
    return OpenMeteoResponse(**json.loads(FIXTURE.read_text()))


def test_all_past_hours_become_rows(): 
    now = datetime(2026, 10, 27, 3, 0, tzinfo=timezone.utc)

    rows = to_rows(load_fixture(), city_id=1, now=now)

    assert len(rows) == 3
    assert rows[0]["city_id"] == 1
    assert rows[0]["ts"] == datetime(2026, 10, 27, 0, 0, tzinfo=timezone.utc)
    assert rows[0]["temperature_2m"] == 7.4


def test_future_hours_are_dropped(): 
    now = datetime(2026, 10, 27, 1, 0, tzinfo=timezone.utc)

    rows = to_rows(load_fixture(), city_id=1, now=now)

    assert len(rows) == 2
    assert rows[-1]["ts"].hour == 1

def test_missing_value_keeps_the_hour():
    # В фикстуре температура за 02:00 = null — час должен сохраниться с пустым полем
    now = datetime(2026, 10, 27, 3, 0, tzinfo=timezone.utc)

    rows = to_rows(load_fixture(), city_id=1, now=now)

    assert rows[2]["temperature_2m"] is None
    assert rows[2]["wind_speed_10m"] == 11.8


def test_lists_of_different_length_raise_error():
    # Температур на одну меньше, чем часов — данные нельзя склеивать со сдвигом
    data = json.loads(FIXTURE.read_text())
    data["hourly"]["temperature_2m"] = [7.4, 7.1]
    now = datetime(2026, 10, 27, 3, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError):
        to_rows(OpenMeteoResponse(**data), city_id=1, now=now)