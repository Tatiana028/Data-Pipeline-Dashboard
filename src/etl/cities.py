from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class City(BaseModel): 

    name: str
    country: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    timezone: str


def load_cities(path: Path) -> list[City]: 
    data = yaml.safe_load(path.read_text())
    return [City(**item) for item in data["cities"]]