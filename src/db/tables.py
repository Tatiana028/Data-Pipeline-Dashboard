from sqlalchemy import (
    Column, 
    Date, 
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)

from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()
 
cities = Table(
    "cities",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100), nullable=False),
    Column("country", String(100), nullable=False),
    Column("latitude", Float, nullable=False),
    Column("longitude", Float, nullable=False),
    Column("timezone", String(64), nullable=False),
    UniqueConstraint("name", "country"),
)


weather_hourly = Table(
    "weather_hourly",
    metadata,
    Column("city_id", Integer, ForeignKey("cities.id"), primary_key=True),
    Column("ts", DateTime(timezone=True), primary_key=True),
    Column("temperature_2m", Float),
    Column("apparent_temperature", Float),
    Column("relative_humidity_2m", Float),
    Column("precipitation", Float),
    Column("wind_speed_10m", Float),
    Column("surface_pressure", Float),
    Column("weather_code", Integer),
    Column("ingested_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Index("ix_weather_hourly_ts", "ts"),
)

 
weather_daily = Table(
    "weather_daily",
    metadata,
    Column("city_id", Integer, ForeignKey("cities.id"), primary_key=True),
    Column("date", Date, primary_key=True),
    Column("temp_min", Float),
    Column("temp_max", Float),
    Column("temp_avg", Float),
    Column("precipitation_sum", Float),
    Column("wind_speed_max", Float),
    Column("humidity_avg", Float),
    Column("hours_count", Integer, nullable=False),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
)
 
etl_runs = Table(
    "etl_runs",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("started_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column("finished_at", DateTime(timezone=True)),
    Column("status", String(20), nullable=False, server_default="running"),
    Column("cities_ok", Integer, nullable=False, server_default="0"),
    Column("cities_failed", Integer, nullable=False, server_default="0"),
    Column("rows_upserted", Integer, nullable=False, server_default="0"),
    Column("error", Text),
    Index("ix_etl_runs_started_at", "started_at"),
)
 
raw_responses = Table(
    "raw_responses",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("city_id", Integer, ForeignKey("cities.id"), nullable=False),
    Column("run_id", Integer, ForeignKey("etl_runs.id"), nullable=False),
    Column("fetched_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column("http_status", Integer, nullable=False),
    Column("payload", JSONB, nullable=False),
)