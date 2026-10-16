from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from pydantic import (
    Base64Bytes,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.modules.route_poles.constants import DEFAULT_RADIUS_M, MAX_RADIUS_M

# Shared by the create, update and read schemas, so the rules stay in one place
CableType = Annotated[str, Field(min_length=1, max_length=50)]
City = Annotated[str, Field(max_length=100)]
IbgeCode = Annotated[str, Field(max_length=10)]
FileName = Annotated[str, Field(max_length=255)]
PolesBase = Annotated[str, Field(max_length=100)]
Radius = Annotated[float, Field(gt=0)]
Count = Annotated[int, Field(ge=0)]
Meters = Annotated[float, Field(ge=0)]
WholeMeters = Annotated[int, Field(ge=0)]
Percent = Annotated[float, Field(ge=0, le=100)]


class CableTypeIn(BaseModel):
    cable_type: CableType
    cables: Count
    # With overlap: every cable's full length
    length_m: WholeMeters
    near_poles: Count
    # Without overlap: a stretch shared by two cables counts for the first
    # one in the KMZ, so the types add up to the summary's route_length_m
    unique_length_m: WholeMeters


class CableIn(BaseModel):
    folder: str
    name: str
    cable_type: CableType
    length_m: Meters
    near_poles: Count
    near_poles_5m: Count
    no_pole_m: WholeMeters
    unique_length_m: Meters


class CityIn(BaseModel):
    """A city a multi-city analysis passes through."""

    city: City
    ibge_code: IbgeCode
    # Empty when no pole base covers the city
    poles_base: PolesBase
    city_poles: Count
    near_poles: Count
    near_poles_pct: Percent


class RouteAnalysisData(BaseModel):
    """An analysis to store, with the KMZ files as bytes."""

    code: str = Field(min_length=1, max_length=255)
    analysis_date: date
    city: City
    ibge_code: IbgeCode
    routes_file: FileName
    poles_base: PolesBase
    radius_m: Radius
    city_poles: Count
    near_poles: Count
    near_poles_pct: Percent
    route_length_m: WholeMeters
    avg_span_m: Meters
    poles_kmz: bytes
    all_poles_kmz: bytes | None = None
    overlap_kmz: bytes | None = None
    with_overlap_kmz: bytes | None = None
    without_overlap_kmz: bytes | None = None
    cable_types: list[CableTypeIn] = Field(max_length=1_000)
    cables: list[CableIn] = Field(max_length=100_000)
    # Only on multi-city analyses
    cities: list[CityIn] = Field(default_factory=list, max_length=1_000)


class RouteAnalysisCreate(RouteAnalysisData):
    """POST /analyses body: the KMZ files go base64-encoded."""

    poles_kmz: Base64Bytes
    all_poles_kmz: Base64Bytes | None = None
    overlap_kmz: Base64Bytes | None = None
    with_overlap_kmz: Base64Bytes | None = None
    without_overlap_kmz: Base64Bytes | None = None


class RouteUploadOptions(BaseModel):
    """Form fields of the upload."""

    city: str | None = Field(
        default=None,
        max_length=100,
        description='City name. Default: detected from the routes',
    )
    ibge_code: str | None = Field(
        default=None,
        pattern=r'^\d{7}$',
        description='IBGE city code, e.g. 3122306',
    )
    radius_m: float = Field(
        default=DEFAULT_RADIUS_M,
        gt=0,
        le=MAX_RADIUS_M,
        description='Max pole-cable distance',
    )
    export_all: bool = Field(
        default=False, description="Also store a KMZ with all the city's poles"
    )
    overlap_kmz: bool = Field(
        default=False,
        description='Also store a KMZ showing what counts and what is overlap',
    )
    overlap_split_kmz: bool = Field(
        default=False,
        description='Also store two KMZ, the cables with overlap and without '
        'it, and return both lengths',
    )

    @field_validator('city', 'ibge_code', mode='before')
    @classmethod
    def blank_to_none(cls, value):
        # Swagger UI (/docs) sends optional form fields filled with 'string'
        if isinstance(value, str) and value.strip() in {'', 'string'}:
            return None
        return value.strip() if isinstance(value, str) else value


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


class RouteAnalysisMultiCreated(RouteAnalysisCreated):
    cities: list[CityIn]


# Updates (PATCH): only the fields sent are changed. The None defaults are
# never validated, so sending null for a field is rejected.
class UpdateModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class RouteAnalysisUpdate(UpdateModel):
    # code is not editable: it identifies the analysis ("ID análise")
    analysis_date: date = None
    city: City = None
    ibge_code: IbgeCode = None
    routes_file: FileName = None
    poles_base: PolesBase = None
    radius_m: Radius = None
    city_poles: Count = None
    near_poles: Count = None
    near_poles_pct: Percent = None
    route_length_m: WholeMeters = None
    avg_span_m: Meters = None


class CableTypeUpdate(UpdateModel):
    cable_type: CableType = None
    cables: Count = None
    length_m: WholeMeters = None
    near_poles: Count = None
    unique_length_m: WholeMeters = None


class CableUpdate(UpdateModel):
    folder: str = None
    name: str = None
    cable_type: CableType = None
    length_m: Meters = None
    near_poles: Count = None
    near_poles_5m: Count = None
    no_pole_m: WholeMeters = None
    unique_length_m: Meters = None


# Reads (JSON). unique_length_m is null for analyses stored before it existed
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


class CityPublic(CityIn):
    model_config = ConfigDict(from_attributes=True)

    id: UUID


class RouteAnalysisPublic(KmzLinks):
    id: UUID
    code: str
    analysis_date: date
    city: str
    ibge_code: str
    routes_file: str
    poles_base: str
    radius_m: float
    city_poles: int
    near_poles: int
    near_poles_pct: float
    route_length_m: int
    avg_span_m: float
    created_at: datetime
    updated_at: datetime


class RouteAnalysisDetail(RouteAnalysisPublic):
    cable_types: list[CableTypePublic]
    cables: list[CablePublic]
    # Empty on single-city analyses
    cities: list[CityPublic]


class BackboneCityAnalysis(RouteAnalysisDetail):
    """A city of a backbone upload: its own analysis."""

    # True when summed into the latest analysis the city already had
    merged: bool


class BackboneCreated(BaseModel):
    cities: list[BackboneCityAnalysis]
