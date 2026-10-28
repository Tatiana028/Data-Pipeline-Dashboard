import os

from sqlalchemy import Engine, create_engine
 
DEFAULT_DATABASE_URL = "postgresql+psycopg://weather:weather@localhost:5432/weather"


def get_engine() -> Engine: 
    return create_engine(os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))