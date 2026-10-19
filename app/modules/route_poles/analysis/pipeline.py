"""Turns an uploaded routes file into the data to store.

Blocking: CPU and network. Raises AnalysisError when the file or the cities
can't be analysed (SourceError when IBGE is down) and OSError when a pole base
can't be downloaded.
"""

import logging
import re
from collections import defaultdict
from datetime import date
from pathlib import PurePath

from ..constants import CLOSE_POLE_M
from ..schemas import (
    AnalysisOptions,
    BackboneData,
    CableIn,
    CableTypeIn,
    CityAnalysisData,
    RouteAnalysisData,
    RouteUploadOptions,
    length_with_overlap,
)
from .city import City, find_cities, find_city
from .city_poles import CityPoles, no_poles_error, poles_in_cities
from .clip import clip_cables
from .engine import RouteResult, analyze
from .errors import AnalysisError
from .geometry import LonLat
from .kmz import (
    KmzKind,
    all_poles_kmz,
    near_poles_kmz,
    overlap_kmz,
    with_overlap_kmz,
    without_overlap_kmz,
)
from .routes import Cable, read_cables

logger = logging.getLogger(__name__)

FIRST_NUMBER = re.compile(r'\d+')

KmzFiles = dict[str, bytes | None]


def run_analysis(
    content: bytes, filename: str, options: RouteUploadOptions
) -> RouteAnalysisData:
    """The analysis of routes inside one city, whole."""
    cables, vertices = read_routes(content)
    city = find_city(vertices, options.city, options.ibge_code)
    found = poles_in_cities([city], vertices)[0]
    if not found.poles:
        raise no_poles_error('this city')

    analysis = analyze_city(city, cables, found, options)
    today = date.today()
    return RouteAnalysisData(
        **dict(analysis),
        code=f'{today.isoformat()}_{city.code}_{PurePath(filename).stem}',
        analysis_date=today,
        routes_file=filename,
        radius_m=options.radius_m,
    )


def run_backbone(
    content: bytes, filename: str, options: AnalysisOptions
) -> BackboneData:
    """The analysis of a backbone: one per city it passes through, each with
    only the stretch of the cables inside the city.
    """
    cables, vertices = read_routes(content)
    cities = find_cities(vertices)
    found = poles_in_cities(cities, vertices)
    if not any(city_found.poles for city_found in found):
        raise no_poles_error('the cities of the routes')

    analyses = []
    for city, city_found in zip(cities, found):
        if city_cables := clip_cables(cables, city.area):
            analyses.append(
                analyze_city(city, city_cables, city_found, options)
            )
    if not analyses:
        raise AnalysisError('No stretch of the routes is inside a city.')

    today = date.today()
    return BackboneData(
        code=f'{today.isoformat()}_{PurePath(filename).stem}',
        backbone_date=today,
        routes_file=filename,
        radius_m=options.radius_m,
        cities=analyses,
    )


def read_routes(content: bytes) -> tuple[list[Cable], list[LonLat]]:
    cables = read_cables(content)
    if not cables:
        raise AnalysisError('No lines found in the file.')
    vertices = [p for cable in cables for line in cable.lines for p in line]
    return cables, vertices


def analyze_city(
    city: City,
    cables: list[Cable],
    found: CityPoles,
    options: AnalysisOptions,
) -> CityAnalysisData:
    """The analysis of cables that are already inside the city."""
    poles = found.poles
    result = analyze(
        cables, poles, options.radius_m, with_stretches=options.with_stretches
    )
    near = result.near_poles
    cable_types = cable_type_rows(cables, options.radius_m)
    logger.info(
        'city analysis: city=%s poles=%d near=%d length=%.0f unique=%.0f',
        city.code,
        len(poles),
        len(near),
        result.total_m,
        result.unique_m,
    )
    return CityAnalysisData(
        city=city.name,
        ibge_code=city.code,
        poles_base=found.base_label,
        city_poles=len(poles),
        near_poles=len(near),
        near_poles_pct=near_pct(len(near), len(poles)),
        route_length_m=route_length(result),
        avg_span_m=average_span(result),
        **point_files(city.name, poles, result, options),
        **cable_files(city.name, cables, cable_types, result, options),
        cable_types=cable_types,
        cables=[cable_row(cable, options.radius_m) for cable in cables],
    )


def point_files(
    city_name: str,
    poles: list[LonLat],
    result: RouteResult,
    options: AnalysisOptions,
) -> KmzFiles:
    return {
        KmzKind.POLES.attr: near_poles_kmz(
            city_name, poles, result, options.radius_m
        ),
        KmzKind.ALL_POLES.attr: (
            all_poles_kmz(city_name, poles) if options.export_all else None
        ),
    }


def cable_files(
    city_name: str,
    cables: list[Cable],
    cable_types: list[CableTypeIn],
    result: RouteResult,
    options: AnalysisOptions,
) -> KmzFiles:
    return {
        KmzKind.OVERLAP.attr: (
            overlap_kmz(f'Sobreposição - {city_name}', result.stretches)
            if options.overlap_kmz
            else None
        ),
        KmzKind.WITH_OVERLAP.attr: (
            with_overlap_kmz(
                f'Cabos com sobreposição - {city_name}',
                cables,
                length_with_overlap(cable_types),
            )
            if options.overlap_split_kmz
            else None
        ),
        KmzKind.WITHOUT_OVERLAP.attr: (
            without_overlap_kmz(
                f'Cabos sem sobreposição - {city_name}',
                result.stretches,
                route_length(result),
            )
            if options.overlap_split_kmz
            else None
        ),
    }


def route_length(result: RouteResult) -> int:
    """Without overlapping cables."""
    return round(result.unique_m)


def average_span(result: RouteResult) -> float:
    near = len(result.near_poles)
    if not near:
        return 0.0
    return round((result.unique_m - result.no_pole_m) / near, 1)


def near_pct(near: int, total: int) -> float:
    return round(100 * near / total, 1) if total else 0.0


def cable_row(cable: Cable, radius_m: float) -> CableIn:
    return CableIn(
        folder=cable.folder,
        name=cable.name,
        cable_type=cable.cable_type,
        length_m=round(cable.length_m, 1),
        near_poles=sum(1 for d in cable.near.values() if d <= radius_m),
        near_poles_5m=sum(1 for d in cable.near.values() if d <= CLOSE_POLE_M),
        no_pole_m=round(cable.no_pole_m),
        unique_length_m=round(cable.unique_length_m, 1),
    )


def cable_type_rows(cables: list[Cable], radius_m: float) -> list[CableTypeIn]:
    by_type: dict[str, list[Cable]] = defaultdict(list)
    for cable in cables:
        by_type[cable.cable_type].append(cable)
    return [
        CableTypeIn(
            cable_type=cable_type,
            cables=len(group),
            length_m=round(sum(c.length_m for c in group)),
            near_poles=len({
                i for c in group for i, d in c.near.items() if d <= radius_m
            }),
            unique_length_m=round(sum(c.unique_length_m for c in group)),
        )
        for cable_type, group in sorted(
            by_type.items(), key=lambda item: type_order(item[0])
        )
    ]


def type_order(cable_type: str) -> tuple[bool, int]:
    """FO-06 before FO-12 before FO-144; "não informado" last."""
    match = FIRST_NUMBER.search(cable_type)
    return match is None, int(match.group()) if match else 0
