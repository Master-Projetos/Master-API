from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.modules.route_poles.schemas import CableIn, CableTypeIn, CityMetrics


class KmzLinks(BaseModel):
    poles_kmz_url: str
    all_poles_kmz_url: str | None
    overlap_kmz_url: str | None
    with_overlap_kmz_url: str | None
    without_overlap_kmz_url: str | None


class RouteAnalysisCreated(KmzLinks):
    id: UUID
    code: str
    # Only with the with/without overlap KMZ; null otherwise
    length_with_overlap_m: int | None = None
    length_without_overlap_m: int | None = None


# unique_length_m is null for analyses stored before it existed
class CableTypePublic(CableTypeIn):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    unique_length_m: int | None
    updated_at: datetime


class CablePublic(CableIn):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    unique_length_m: float | None
    updated_at: datetime


class RouteAnalysisPublic(CityMetrics, KmzLinks):
    id: UUID
    code: str
    analysis_date: date
    routes_file: str
    radius_m: float
    created_at: datetime
    updated_at: datetime


class RouteAnalysisDetail(RouteAnalysisPublic):
    cable_types: list[CableTypePublic]
    cables: list[CablePublic]
