from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel

from app.modules.route_poles.schemas import CityMetrics

from .schemas import CablePublic, CableTypePublic, KmzLinks


class BackboneCityPublic(CityMetrics, KmzLinks):
    id: UUID


class BackboneCityDetail(BackboneCityPublic):
    cable_types: list[CableTypePublic]
    cables: list[CablePublic]


class BackbonePublic(BaseModel):
    id: UUID
    code: str
    backbone_date: date
    routes_file: str
    radius_m: float
    created_at: datetime
    updated_at: datetime
    cities_count: int
    # Sums of the cities
    route_length_m: int
    near_poles: int
    cities: list[BackboneCityPublic]


class BackboneDetail(BackbonePublic):
    cities: list[BackboneCityDetail]
