from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.route_poles.analysis.kmz import KmzKind
from app.modules.route_poles.constants import DEFAULT_RADIUS_M, MAX_RADIUS_M

CableType = Annotated[str, Field(min_length=1, max_length=50)]
CityName = Annotated[str, Field(max_length=100)]
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
    # one in the KMZ, so the types add up to the city's route_length_m
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


def length_with_overlap(cable_types: list[CableTypeIn]) -> int:
    return sum(row.length_m for row in cable_types)


class CityMetrics(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    city: CityName
    ibge_code: IbgeCode
    # Empty when no pole base covers the city
    poles_base: PolesBase
    city_poles: Count
    near_poles: Count
    near_poles_pct: Percent
    # Without overlap
    route_length_m: WholeMeters
    avg_span_m: Meters


class CityAnalysisData(CityMetrics):
    """The analysis of one city, with the KMZ files as bytes."""

    poles_kmz: bytes
    all_poles_kmz: bytes | None = None
    overlap_kmz: bytes | None = None
    with_overlap_kmz: bytes | None = None
    without_overlap_kmz: bytes | None = None
    # The vertices of the cables, to compare them with the licensed poles
    cable_lines: bytes | None = None
    cable_types: list[CableTypeIn] = Field(max_length=1_000)
    cables: list[CableIn] = Field(max_length=100_000)

    @property
    def length_with_overlap_m(self) -> int:
        return length_with_overlap(self.cable_types)

    @property
    def kmz_kinds(self) -> frozenset[KmzKind]:
        return frozenset(
            kind for kind in KmzKind if getattr(self, kind.attr) is not None
        )

    def columns(self) -> dict:
        """The values of the model columns."""
        return self.model_dump(exclude={'cable_types', 'cables'})


class RouteAnalysisData(CityAnalysisData):
    code: str = Field(min_length=1, max_length=255)
    analysis_date: date
    routes_file: FileName
    radius_m: Radius


class BackboneData(BaseModel):
    """A backbone: its analysis in each city it passes through."""

    code: str = Field(min_length=1, max_length=255)
    backbone_date: date
    routes_file: FileName
    radius_m: Radius
    cities: list[CityAnalysisData] = Field(min_length=1, max_length=1_000)


class LicensedCityData(BaseModel):
    city: CityName
    ibge_code: IbgeCode
    # lon, lat, name
    markers: list[tuple[float, float, str]] = Field(min_length=1)


class LicensedData(BaseModel):
    """The licensed poles of a file, by the city they are in."""

    code: str = Field(min_length=1, max_length=255)
    set_date: date
    licensed_file: FileName
    cities: list[LicensedCityData] = Field(max_length=1_000)
    # Inside no city of MG and SP
    outside_markers: list[tuple[float, float, str]]


class AnalysisOptions(BaseModel):
    """Form fields of an upload."""

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

    @property
    def with_stretches(self) -> bool:
        return self.overlap_kmz or self.overlap_split_kmz


class RouteUploadOptions(AnalysisOptions):
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

    @field_validator('city', 'ibge_code', mode='before')
    @classmethod
    def blank_to_none(cls, value):
        # Swagger UI (/docs) sends optional form fields filled with 'string'
        if isinstance(value, str) and value.strip() in {'', 'string'}:
            return None
        return value.strip() if isinstance(value, str) else value


class BackboneSearch(BaseModel):
    """A backbone matches when it has a city with the IBGE code and name."""

    model_config = ConfigDict(extra='forbid')

    ibge_code: str | None = Field(
        default=None, max_length=10, description='IBGE code of a city'
    )
    city: str | None = Field(
        default=None, max_length=100, description='Part of a city name'
    )
    routes_file: str | None = Field(
        default=None, max_length=255, description='Part of the file name'
    )
    date_from: date | None = None
    date_to: date | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
