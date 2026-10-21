from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel

from app.modules.route_poles.jobs import JobStatus
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


class BackboneJobPublic(BaseModel):
    id: UUID
    filename: str
    status: JobStatus
    stage: str
    cities_done: int
    cities_total: int
    current_city: str | None
    error: str | None
    created_at: datetime
    finished_at: datetime | None
    backbone_id: UUID | None
    backbone_code: str | None
    backbone_url: str | None
    # Set when the job came with licensed poles: read their comparison there
    licensed_code: str | None
    licensed_url: str | None
