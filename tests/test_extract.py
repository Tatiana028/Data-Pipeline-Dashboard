import httpx
import pytest
import respx
from tenacity import wait_none

from src.etl.cities import City
from src.etl.extract import OPEN_METEO_URL, fetch_weather

BERLIN = City(
    name="Berlin", country="Germany", latitude=52.52, longitude=13.41, timezone="Europe/Berlin"
)


@pytest.fixture(autouse=True)
def no_wait(monkeypatch): 
    monkeypatch.setattr(fetch_weather.retry, "wait", wait_none())


@respx.mock
def test_retries_then_succeeds():
    # Сервер дважды "моргнул" (503), на третий раз ответил нормально
    route = respx.get(OPEN_METEO_URL).mock(
        side_effect=[httpx.Response(503), httpx.Response(503), httpx.Response(200, json={})]
    )

    response = fetch_weather(BERLIN, past_days=1)

    assert response.status_code == 200
    assert route.call_count == 3


@respx.mock
def test_gives_up_after_three_attempts(): 
    route = respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(503))

    with pytest.raises(httpx.HTTPStatusError):
        fetch_weather(BERLIN, past_days=1)

    assert route.call_count == 3


@respx.mock
def test_no_retry_on_client_error(): 
    route = respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(400))

    with pytest.raises(httpx.HTTPStatusError):
        fetch_weather(BERLIN, past_days=1)

    assert route.call_count == 1