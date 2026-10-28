import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
 
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://weather:weather@localhost:5432/weather_test"
)
PROJECT_ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="session")
def engine(): 
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    engine = create_engine(TEST_DATABASE_URL)
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine): 
    with engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE cities, weather_hourly, weather_daily, raw_responses, etl_runs "
            "RESTART IDENTITY CASCADE"
        ))
    return engine
