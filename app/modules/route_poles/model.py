from datetime import date
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Date, ForeignKey, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class RouteAnalysis(Base):
    """One analysis: a routes KMZ crossed with the pole bases."""

    __tablename__ = 'route_analyses'

    # '<date>_<ibge_code>_<routes file>'; sending it again replaces the row
    code: Mapped[str] = mapped_column(String(255), unique=True)
    analysis_date: Mapped[date] = mapped_column(Date, index=True)
    city: Mapped[str] = mapped_column(String(100))
    ibge_code: Mapped[str] = mapped_column(String(10), index=True)
    routes_file: Mapped[str] = mapped_column(String(255))
    poles_base: Mapped[str] = mapped_column(String(100))
    radius_m: Mapped[float]

    city_poles: Mapped[int]
    near_poles: Mapped[int]
    near_poles_pct: Mapped[float]
    # Route length without overlapping cables
    route_length_m: Mapped[int]
    avg_span_m: Mapped[float]

    # Deferred: only loaded by the download routes
    poles_kmz: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    # Only when the script ran with --exportar-todos
    all_poles_kmz: Mapped[bytes | None] = mapped_column(
        LargeBinary, deferred=True
    )
    # Only with --kmz-sobreposicao: what counts and what is overlap
    overlap_kmz: Mapped[bytes | None] = mapped_column(
        LargeBinary, deferred=True
    )

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


class KmzKind(StrEnum):
    """The KMZ files an analysis can have; the value is the download path."""

    POLES = 'poles'
    ALL_POLES = 'all-poles'
    OVERLAP = 'overlap'

    @property
    def column(self):
        return {
            KmzKind.POLES: RouteAnalysis.poles_kmz,
            KmzKind.ALL_POLES: RouteAnalysis.all_poles_kmz,
            KmzKind.OVERLAP: RouteAnalysis.overlap_kmz,
        }[self]


class RouteCableType(Base):
    __tablename__ = 'route_cable_types'

    analysis_id: Mapped[UUID] = mapped_column(
        ForeignKey('route_analyses.id', ondelete='CASCADE'), index=True
    )
    cable_type: Mapped[str] = mapped_column(String(50))
    cables: Mapped[int]
    # With overlap
    length_m: Mapped[int]
    near_poles: Mapped[int]
    # Without overlap; null on analyses stored before it existed
    unique_length_m: Mapped[int | None]


class RouteCable(Base):
    __tablename__ = 'route_cables'

    analysis_id: Mapped[UUID] = mapped_column(
        ForeignKey('route_analyses.id', ondelete='CASCADE'), index=True
    )
    folder: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    cable_type: Mapped[str] = mapped_column(String(50))
    length_m: Mapped[float]
    near_poles: Mapped[int]
    near_poles_5m: Mapped[int]
    # Stretch of the cable with no pole closer than 25 m
    no_pole_m: Mapped[int]
    # Length not shared with a cable that comes before it in the KMZ; null on
    # analyses stored before it existed
    unique_length_m: Mapped[float | None]
