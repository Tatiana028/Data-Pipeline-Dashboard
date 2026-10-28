import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from src.etl.cities import City

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
 
HOURLY_METRICS = [
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "precipitation",
    "wind_speed_10m",
    "surface_pressure",
    "weather_code",
]

def _is_retryable(exc: BaseException) -> bool: 
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status >= 500 or status == 429
    return False

@retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, max=10),
    reraise=True,
) 
def fetch_weather(city: City, past_days: int) -> httpx.Response:
     
    params = {
        "latitude": city.latitude,
        "longitude": city.longitude,
        "hourly": ",".join(HOURLY_METRICS),
        "past_days": past_days,
        "forecast_days": 1,
        "timezone": "UTC",
    }
    response = httpx.get(OPEN_METEO_URL, params=params, timeout=10)
    response.raise_for_status()
    return response