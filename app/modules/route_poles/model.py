from collections.abc import Iterable
from datetime import date
from typing import NamedTuple
from uuid import UUID

from sqlalchemy import (
    JSON,
    ColumnElement,
    Date,
    ForeignKey,
    LargeBinary,
    Select,
    String,
    Text,
    UniqueConstraint,
    select,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.modules.route_poles.analysis.kmz import KmzKind

# Every kind but the first has a nullable column
OPTIONAL_KMZ = tuple(kind for kind in KmzKind if kind != KmzKind.POLES)


class CityMetrics:
    city: Mapped[str] = mapped_column(String(100))
    ibge_code: Mapped[str] = mapped_column(String(10), index=True)
    poles_base: Mapped[str] = mapped_column(String(100))
    city_poles: Mapped[int]
    near_poles: Mapped[int]
    near_poles_pct: Mapped[float]
    # Without overlapping cables
    route_length_m: Mapped[int]
    avg_span_m: Mapped[float]


class KmzFiles:
    # Deferred: only loaded by the download routes
    poles_kmz: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    # Only with the "export all" option
    all_poles_kmz: Mapped[bytes | None] = mapped_column(
        LargeBinary, deferred=True
    )
    # Only with the overlap option: what counts and what is overlap
    overlap_kmz: Mapped[bytes | None] = mapped_column(
        LargeBinary, deferred=True
    )
    # Only with the overlap split option: the cables whole, and only what
    # counts
    with_overlap_kmz: Mapped[bytes | None] = mapped_column(
        LargeBinary, deferred=True
    )
    without_overlap_kmz: Mapped[bytes | None] = mapped_column(
        LargeBinary, deferred=True
    )

    @classmethod
    def kmz_flags(cls) -> list[ColumnElement[bool]]:
        """For each optional KMZ, whether it exists, without loading it."""
        return [getattr(cls, kind.attr).is_not(None) for kind in OPTIONAL_KMZ]

    @classmethod
    def select_with_kmz_kinds(cls) -> Select:
        return select(cls, *cls.kmz_flags())


class CableLines:
    # Deferred: only loaded to compare the city with the licensed poles. Null
    # in the rows saved before it was kept
    cable_lines: Mapped[bytes | None] = mapped_column(
        LargeBinary, deferred=True
    )


def kmz_kinds(flags: Iterable[bool]) -> frozenset[KmzKind]:
    """The kinds of a row selected with the kmz_flags."""
    return frozenset([
        KmzKind.POLES,
        *(kind for kind, has in zip(OPTIONAL_KMZ, flags) if has),
    ])


class StoredKmz(NamedTuple):
    # Identifies the file in its download name
    name: str
    content: bytes


class CableTypeColumns:
    cable_type: Mapped[str] = mapped_column(String(50))
    cables: Mapped[int]
    # With overlap
    length_m: Mapped[int]
    near_poles: Mapped[int]


class CableColumns:
    folder: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    cable_type: Mapped[str] = mapped_column(String(50))
    length_m: Mapped[float]
    near_poles: Mapped[int]
    near_poles_5m: Mapped[int]
    # Stretch of the cable with no pole closer than NO_POLE_M
    no_pole_m: Mapped[int]


def ref_condition(model, ref: str) -> ColumnElement[bool]:
    """A row is referenced by id (UUID) or by code."""
    try:
        return model.id == UUID(ref)
    except ValueError:
        return model.code == ref


class RouteAnalysis(CityMetrics, KmzFiles, CableLines, Base):
    """One analysis: a routes KMZ crossed with the pole bases."""

    __tablename__ = 'route_analyses'

    # '<date>_<ibge_code>_<routes file>'; sending it again replaces the row
    code: Mapped[str] = mapped_column(String(255), unique=True)
    analysis_date: Mapped[date] = mapped_column(Date, index=True)
    routes_file: Mapped[str] = mapped_column(String(255))
    radius_m: Mapped[float]

    cable_types: Mapped[list['RouteCableType']] = relationship(
        cascade='all, delete-orphan',
        passive_deletes=True,
        order_by='RouteCableType.cable_type',
    )
    cables: Mapped[list['RouteCable']] = relationship(
        cascade='all, delete-orphan',
        passive_deletes=True,
        order_by='(RouteCable.folder, RouteCable.name)',
    )


class RouteCableType(CableTypeColumns, Base):
    __tablename__ = 'route_cable_types'

    analysis_id: Mapped[UUID] = mapped_column(
        ForeignKey('route_analyses.id', ondelete='CASCADE'), index=True
    )
    # Without overlap; null on analyses stored before it existed
    unique_length_m: Mapped[int | None]


class RouteCable(CableColumns, Base):
    __tablename__ = 'route_cables'

    analysis_id: Mapped[UUID] = mapped_column(
        ForeignKey('route_analyses.id', ondelete='CASCADE'), index=True
    )
    # Length not shared with a cable that comes before it in the KMZ; null on
    # analyses stored before it existed
    unique_length_m: Mapped[float | None]


class Backbone(Base):
    """A backbone upload: one analysis per city it passes through."""

    __tablename__ = 'backbones'

    # '<date>_<routes file>'; sending it again replaces the row
    code: Mapped[str] = mapped_column(String(255), unique=True)
    backbone_date: Mapped[date] = mapped_column(Date, index=True)
    routes_file: Mapped[str] = mapped_column(String(255))
    radius_m: Mapped[float]

    cities: Mapped[list['BackboneCity']] = relationship(
        cascade='all, delete-orphan',
        passive_deletes=True,
        order_by='BackboneCity.city',
    )


class BackboneCity(CityMetrics, KmzFiles, CableLines, Base):
    __tablename__ = 'backbone_cities'
    __table_args__ = (UniqueConstraint('backbone_id', 'ibge_code'),)

    backbone_id: Mapped[UUID] = mapped_column(
        ForeignKey('backbones.id', ondelete='CASCADE'), index=True
    )

    cable_types: Mapped[list['BackboneCableType']] = relationship(
        cascade='all, delete-orphan',
        passive_deletes=True,
        order_by='BackboneCableType.cable_type',
    )
    cables: Mapped[list['BackboneCable']] = relationship(
        cascade='all, delete-orphan',
        passive_deletes=True,
        order_by='(BackboneCable.folder, BackboneCable.name)',
    )


class LicensedSet(Base):
    """A file of licensed poles. Only the markers are stored: what they are
    compared with is whatever analysis of each city is the latest when read.
    """

    __tablename__ = 'licensed_pole_sets'

    # '<date>_<licensed file>'; sending it again replaces the row
    code: Mapped[str] = mapped_column(String(255), unique=True)
    set_date: Mapped[date] = mapped_column(Date, index=True)
    licensed_file: Mapped[str] = mapped_column(String(255))
    # Markers inside no city of MG and SP, as [lon, lat, name]
    outside_poles: Mapped[int]
    outside_markers: Mapped[list] = mapped_column(JSON, deferred=True)

    cities: Mapped[list['LicensedCity']] = relationship(
        cascade='all, delete-orphan',
        passive_deletes=True,
        order_by='LicensedCity.city',
    )


class LicensedCity(Base):
    __tablename__ = 'licensed_pole_cities'
    __table_args__ = (UniqueConstraint('set_id', 'ibge_code'),)

    set_id: Mapped[UUID] = mapped_column(
        ForeignKey('licensed_pole_sets.id', ondelete='CASCADE'), index=True
    )
    city: Mapped[str] = mapped_column(String(100))
    ibge_code: Mapped[str] = mapped_column(String(10), index=True)
    poles: Mapped[int]
    # [lon, lat, name]
    markers: Mapped[list] = mapped_column(JSON, deferred=True)


class BackboneCableType(CableTypeColumns, Base):
    __tablename__ = 'backbone_cable_types'

    backbone_city_id: Mapped[UUID] = mapped_column(
        ForeignKey('backbone_cities.id', ondelete='CASCADE'), index=True
    )
    unique_length_m: Mapped[int]


class BackboneCable(CableColumns, Base):
    __tablename__ = 'backbone_cables'

    backbone_city_id: Mapped[UUID] = mapped_column(
        ForeignKey('backbone_cities.id', ondelete='CASCADE'), index=True
    )
    unique_length_m: Mapped[float]
