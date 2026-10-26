from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class LicensedSetSummary(BaseModel):
    id: UUID
    code: str
    set_date: date
    licensed_file: str
    created_at: datetime
    updated_at: datetime
    cities_count: int
    # Including the ones outside the cities
    licensed_poles: int
    outside_poles: int


class LicensedSource(BaseModel):
    """An analysis whose poles in use the city was compared with."""

    kind: Literal['backbone', 'analysis']
    code: str
    source_date: date


class LicensedCityResult(BaseModel):
    city: str
    ibge_code: str
    licensed_poles: int
    # pending: no analysis of the city is stored yet
    status: Literal['compared', 'pending']
    # The latest of the sources, null while pending
    source: LicensedSource | None
    # Every source compared: the backbones and the latest analysis
    sources: list[LicensedSource]
    # Null while pending
    used_poles: int | None
    matched: int | None
    unlicensed: int | None
    unused: int | None


class LicensedSetDetail(LicensedSetSummary):
    """matched + unused is the licensed poles of the compared cities and
    matched + unlicensed is their poles in use.
    """

    # Max distance between a licensed marker and the pole in use it matches
    tolerance_m: float
    matched: int
    unlicensed: int
    unused: int
    # Licensed poles of the cities with no analysis yet
    pending_poles: int
    comparison_kmz_url: str
    cities: list[LicensedCityResult]
