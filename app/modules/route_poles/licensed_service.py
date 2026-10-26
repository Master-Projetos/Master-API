import asyncio
from dataclasses import dataclass
from datetime import date, datetime
from typing import NamedTuple
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, undefer

from app.modules.route_poles.analysis.geometry import LonLat
from app.modules.route_poles.analysis.licensing import (
    CityComparison,
    Lines,
    compare_city,
    decode_cable_lines,
    poles_near,
)
from app.modules.route_poles.analysis.routes import Marker, read_markers
from app.modules.route_poles.constants import LICENSED_CABLE_M, SAME_POLE_M
from app.modules.route_poles.model import (
    Backbone,
    BackboneCity,
    LicensedCity,
    LicensedSet,
    RouteAnalysis,
    ref_condition,
)
from app.modules.route_poles.schemas import LicensedData


class UsedSource(NamedTuple):
    """An analysis whose poles in use a city is compared with."""

    kind: str
    code: str
    source_date: date
    created_at: datetime
    # The id of the backbone city or of the analysis
    row_id: UUID
    # Of the analysis: a marker is in use with a cable this near, or within
    # LICENSED_CABLE_M
    radius_m: float


class UsedFiles(NamedTuple):
    poles_kmz: bytes
    # None for an analysis saved before the cables were kept
    cable_lines: bytes | None


@dataclass(frozen=True)
class CityResult:
    city: LicensedCity
    # Every backbone and the latest analysis of the city, the latest first.
    # Empty while none is stored
    sources: list[UsedSource]
    comparison: CityComparison | None


@dataclass(frozen=True)
class SetResult:
    cities: list[CityResult]
    outside: list[Marker]


async def save_licensed(session: AsyncSession, data: LicensedData) -> UUID:
    # Sending the same file again replaces it, so a retry never duplicates
    await session.execute(
        delete(LicensedSet).where(LicensedSet.code == data.code)
    )
    # The new licensing of a city replaces the one it had in any other set
    await session.execute(
        delete(LicensedCity).where(
            LicensedCity.ibge_code.in_([c.ibge_code for c in data.cities])
        )
    )
    await session.execute(
        delete(LicensedSet).where(
            LicensedSet.outside_poles == 0,
            ~select(LicensedCity.id)
            .where(LicensedCity.set_id == LicensedSet.id)
            .exists(),
        )
    )
    licensed = LicensedSet(
        code=data.code,
        set_date=data.set_date,
        licensed_file=data.licensed_file,
        outside_poles=len(data.outside_markers),
        outside_markers=[list(m) for m in data.outside_markers],
        cities=[
            LicensedCity(
                city=city.city,
                ibge_code=city.ibge_code,
                poles=len(city.markers),
                markers=[list(m) for m in city.markers],
            )
            for city in data.cities
        ],
    )
    session.add(licensed)
    await session.commit()
    return licensed.id


async def list_licensed(
    session: AsyncSession, limit: int, offset: int
) -> list[LicensedSet]:
    query = (
        select(LicensedSet)
        .options(selectinload(LicensedSet.cities))
        .order_by(LicensedSet.set_date.desc(), LicensedSet.code)
        .limit(limit)
        .offset(offset)
    )
    return list((await session.scalars(query)).all())


async def get_licensed(
    session: AsyncSession, ref: str, with_markers: bool = False
) -> LicensedSet | None:
    cities = selectinload(LicensedSet.cities)
    query = select(LicensedSet).where(ref_condition(LicensedSet, ref))
    if with_markers:
        cities = cities.options(undefer(LicensedCity.markers))
        query = query.options(undefer(LicensedSet.outside_markers))
    return await session.scalar(query.options(cities))


async def delete_licensed(session: AsyncSession, ref: str) -> bool:
    deleted_id = await session.scalar(
        delete(LicensedSet)
        .where(ref_condition(LicensedSet, ref))
        .returning(LicensedSet.id)
    )
    await session.commit()
    return deleted_id is not None


async def latest_sources(
    session: AsyncSession, ibge_codes: list[str]
) -> dict[str, list[UsedSource]]:
    """For each IBGE code, every stored backbone city and its latest analysis,
    the latest first. The poles in use of a city are the ones of all of them:
    each backbone covers other routes of the city, and a single-city analysis
    replaces the earlier ones.
    """
    backbones = await session.execute(
        select(
            BackboneCity.ibge_code,
            Backbone.code,
            Backbone.backbone_date,
            BackboneCity.created_at,
            BackboneCity.id,
            Backbone.radius_m,
        )
        .join(Backbone, BackboneCity.backbone_id == Backbone.id)
        .where(BackboneCity.ibge_code.in_(ibge_codes))
    )
    analyses = await session.execute(
        select(
            RouteAnalysis.ibge_code,
            RouteAnalysis.code,
            RouteAnalysis.analysis_date,
            RouteAnalysis.created_at,
            RouteAnalysis.id,
            RouteAnalysis.radius_m,
        ).where(RouteAnalysis.ibge_code.in_(ibge_codes))
    )
    by_city: dict[str, list[UsedSource]] = {}
    latest_analysis: dict[str, UsedSource] = {}
    for ibge_code, code, source_date, created_at, row_id, radius in backbones:
        by_city.setdefault(ibge_code, []).append(
            UsedSource(
                'backbone', code, source_date, created_at, row_id, radius
            )
        )
    for ibge_code, code, source_date, created_at, row_id, radius in analyses:
        source = UsedSource(
            'analysis', code, source_date, created_at, row_id, radius
        )
        best = latest_analysis.get(ibge_code)
        if best is None or (source.source_date, source.created_at) > (
            best.source_date,
            best.created_at,
        ):
            latest_analysis[ibge_code] = source
    for ibge_code, source in latest_analysis.items():
        by_city.setdefault(ibge_code, []).append(source)
    for sources in by_city.values():
        sources.sort(key=lambda s: (s.source_date, s.created_at), reverse=True)
    return by_city


async def used_files(
    session: AsyncSession, sources: dict[str, list[UsedSource]]
) -> dict[UUID, UsedFiles]:
    """The files of the poles in use of each source, by row id."""
    files: dict[UUID, UsedFiles] = {}
    for model, kind in (
        (BackboneCity, 'backbone'),
        (RouteAnalysis, 'analysis'),
    ):
        ids = [
            source.row_id
            for city_sources in sources.values()
            for source in city_sources
            if source.kind == kind
        ]
        if not ids:
            continue
        rows = await session.execute(
            select(model.id, model.poles_kmz, model.cable_lines).where(
                model.id.in_(ids)
            )
        )
        files.update({
            row_id: UsedFiles(poles_kmz, cable_lines)
            for row_id, poles_kmz, cable_lines in rows
        })
    return files


async def compare_licensed(
    session: AsyncSession, licensed: LicensedSet
) -> SetResult:
    """The licensed poles of each city against the poles in use of its
    backbones and its latest analysis. The markers of the set must be loaded.
    """
    sources = await latest_sources(
        session, [city.ibge_code for city in licensed.cities]
    )
    files = await used_files(session, sources)
    return await asyncio.to_thread(compare_sources, licensed, sources, files)


def compare_sources(
    licensed: LicensedSet,
    sources: dict[str, list[UsedSource]],
    files: dict[UUID, UsedFiles],
) -> SetResult:
    """Blocking: parses the files and compares the poles."""
    results = []
    for city in licensed.cities:
        city_sources = sources.get(city.ibge_code, [])
        comparison = None
        if city_sources:
            used, cables = merge_used(city_sources, files)
            comparison = compare_city(
                [tuple(m) for m in city.markers], used, cables=cables
            )
        results.append(CityResult(city, city_sources, comparison))
    return SetResult(results, [tuple(m) for m in licensed.outside_markers])


def merge_used(
    sources: list[UsedSource], files: dict[UUID, UsedFiles]
) -> tuple[list[LonLat], list[tuple[Lines, float]]]:
    """The poles in use of the sources, a pole in two of them only once, and
    the cables of the sources that have them.
    """
    used: list[LonLat] = []
    cables = []
    for source in sources:
        stored = files[source.row_id]
        poles = [m[:2] for m in read_markers(stored.poles_kmz)]
        repeated = poles_near(poles, used, SAME_POLE_M)
        used.extend(p for i, p in enumerate(poles) if i not in repeated)
        if stored.cable_lines:
            cables.append((
                decode_cable_lines(stored.cable_lines),
                max(source.radius_m, LICENSED_CABLE_M),
            ))
    return used, cables
