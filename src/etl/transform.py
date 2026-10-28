from datetime import datetime, timezone

from pydantic import BaseModel


class HourlyData(BaseModel): 

    time: list[datetime]
    temperature_2m: list[float | None]
    apparent_temperature: list[float | None]
    relative_humidity_2m: list[float | None]
    precipitation: list[float | None]
    wind_speed_10m: list[float | None]
    surface_pressure: list[float | None]
    weather_code: list[int | None]


class OpenMeteoResponse(BaseModel): 

    hourly: HourlyData

def to_rows(response: OpenMeteoResponse, city_id: int, now: datetime) -> list[dict]: 
    
    h = response.hourly
    rows = []
    for ts, temp, app_temp, humidity, precip, wind, pressure, code in zip(
        h.time,
        h.temperature_2m,
        h.apparent_temperature,
        h.relative_humidity_2m,
        h.precipitation,
        h.wind_speed_10m,
        h.surface_pressure,
        h.weather_code,
        strict=True,
    ):
        ts = ts.replace(tzinfo=timezone.utc)
        if ts > now:
            continue
        rows.append(
            {
                "city_id": city_id,
                "ts": ts,
                "temperature_2m": temp,
                "apparent_temperature": app_temp,
                "relative_humidity_2m": humidity,
                "precipitation": precip,
                "wind_speed_10m": wind,
                "surface_pressure": pressure,
                "weather_code": code,
            }
        )
    return rows