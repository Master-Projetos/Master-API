import csv
import io
import logging
import math
import re
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import date
from pathlib import PurePath
from uuid import UUID

from sqlalchemy import ColumnElement, Select, delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v8.route_poles.schemas import (
    CableIn,
    CableTypeIn,
    CityIn,
    RouteAnalysisData,
    RouteUploadOptions,
)
from app.modules.route_poles.analysis.city import City, find_cities, find_city
from app.modules.route_poles.analysis.engine import RouteResult, analyze
from app.modules.route_poles.analysis.errors import AnalysisError, SourceError
from app.modules.route_poles.analysis.kmz import (
    overlap_kmz,
    points_kmz,
    with_overlap_kmz,
    without_overlap_kmz,
)
from app.modules.route_poles.analysis.pole_base import (
    POLE_BASES,
    local_bases,
    read_poles,
)
from app.modules.route_poles.analysis.routes import Cable, read_cables
from app.modules.route_poles.constants import BASE_MIN_SHARE, CLOSE_POLE_M
from app.modules.route_poles.model import (
    KmzKind,
    RouteAnalysis,
    RouteAnalysisCity,
    RouteCable,
    RouteCableType,
)

logger = logging.getLogger(__name__)

# Re-exported for the router
__all__ = ['AnalysisError', 'SourceError']

# CSV headers are in Portuguese: they become the Google Sheets columns. New
# columns go at the end, so the sheet's formulas keep their references
SUMMARY_HEADER = [
    'ID análise',
    'Data',
    'Município',
    'Código IBGE',
    'Arquivo de rotas',
    'Base de postes',
    'Raio (m)',
    'Postes totais no município',
    'Postes próximos aos cabos',
    '% dos postes da cidade',
    'Metragem total sem sobreposição (m)',
    'Vão médio estimado (m)',
    'KMZ postes utilizados',
    'KMZ todos os postes',
    'KMZ sobreposição',
    'KMZ com sobreposição',
    'KMZ sem sobreposição',
]
CABLE_TYPES_HEADER = [
    'ID análise',
    'Data',
    'Município',
    'Arquivo de rotas',
    'Tipo de cabo',
    'Cabos',
    'Metros',
    'Postes próximos',
    'Metros sem sobreposição',
]
CABLES_HEADER = [
    'ID análise',
    'Pasta',
    'Cabo',
    'Tipo de cabo',
    'Metros',
    'Postes no raio',
    'Postes a até 5 m',
    'Trecho sem poste a <25 m (m)',
    'Metros sem sobreposição',
]

KmzLink = Callable[[UUID, KmzKind], str]
LonLat = tuple[float, float]

# Margin (degrees) around the city when reading the pole tiles
BBOX_MARGIN = 0.001
FIRST_NUMBER = re.compile(r'\d+')
# Max length of the city and poles_base columns
LABEL_MAX = 100
# Sampling step (degrees, ~11 m) and precision of the cut at a city border
CLIP_STEP = 1e-4
CLIP_BISECTIONS = 30


def run_analysis(
    content: bytes, filename: str, options: RouteUploadOptions
) -> RouteAnalysisData:
    """Analyses an uploaded routes KMZ/KML. Blocking: CPU and network.

    Raises AnalysisError when the file or the city can't be analysed
    (SourceError when IBGE is down) and OSError when a pole base can't be
    downloaded.
    """
    cables = read_cables(content)
    if not cables:
        raise AnalysisError('Nenhuma linha encontrada no arquivo.')
    vertices = [p for c in cables for line in c.lines for p in line]
    city = find_city(vertices, options.city, options.ibge_code)
    poles, poles_base = city_poles(city, vertices)

    result = analyze(
        cables,
        poles,
        options.radius_m,
        with_stretches=options.overlap_kmz or options.overlap_split_kmz,
    )
    near = result.near_poles
    cable_types = cable_type_rows(cables, options.radius_m)
    route_length_m = round(result.unique_m)
    logger.info(
        'route analysis: city=%s poles=%d near=%d length=%.0f unique=%.0f',
        city.code,
        len(poles),
        len(near),
        result.total_m,
        result.unique_m,
    )

    today = date.today()
    return RouteAnalysisData(
        code=f'{today.isoformat()}_{city.code}_{PurePath(filename).stem}',
        analysis_date=today,
        city=city.name,
        ibge_code=city.code,
        routes_file=filename,
        poles_base=poles_base,
        radius_m=options.radius_m,
        city_poles=len(poles),
        near_poles=len(near),
        near_poles_pct=round(100 * len(near) / len(poles), 1),
        route_length_m=route_length_m,
        avg_span_m=round(
            (result.unique_m - result.no_pole_m) / len(near) if near else 0.0,
            1,
        ),
        poles_kmz=near_poles_kmz(city, poles, result, options.radius_m),
        all_poles_kmz=(
            all_poles_kmz(city, poles) if options.export_all else None
        ),
        overlap_kmz=(
            overlap_kmz(f'Sobreposição - {city.name}', result.stretches)
            if options.overlap_kmz
            else None
        ),
        with_overlap_kmz=(
            with_overlap_kmz(
                f'Cabos com sobreposição - {city.name}',
                cables,
                length_with_overlap(cable_types),
            )
            if options.overlap_split_kmz
            else None
        ),
        without_overlap_kmz=(
            without_overlap_kmz(
                f'Cabos sem sobreposição - {city.name}',
                result.stretches,
                route_length_m,
            )
            if options.overlap_split_kmz
            else None
        ),
        cable_types=cable_types,
        cables=[cable_row(c, options.radius_m) for c in cables],
    )


def run_multi_city_analysis(
    content: bytes, filename: str, options: RouteUploadOptions
) -> RouteAnalysisData:
    """Like run_analysis, for routes that pass through several cities.

    The summary fields add up every city; the main city (ibge_code, code)
    is the one with most near poles. Each city goes in cities.
    """
    cables = read_cables(content)
    if not cables:
        raise AnalysisError('Nenhuma linha encontrada no arquivo.')
    vertices = [p for c in cables for line in c.lines for p in line]
    cities = find_cities(vertices)
    by_city = cities_poles(cities, vertices)
    poles = [p for city_poles_, _ in by_city for p in city_poles_]
    if not poles:
        utilities = ', '.join(b.utility for b in POLE_BASES)
        raise AnalysisError(
            f'Nenhum poste das bases ({utilities}) nos municípios das rotas '
            '(área de outra distribuidora?).'
        )

    result = analyze(
        cables,
        poles,
        options.radius_m,
        with_stretches=options.overlap_kmz or options.overlap_split_kmz,
    )
    near = result.near_poles
    city_rows = city_near_rows(cities, by_city, near)
    main = cities[
        max(range(len(cities)), key=lambda k: city_rows[k].near_poles)
    ]
    label = cities_label([c.name for c in cities])
    cable_types = cable_type_rows(cables, options.radius_m)
    route_length_m = round(result.unique_m)
    logger.info(
        'multi-city route analysis: cities=%s poles=%d near=%d unique=%.0f',
        ','.join(c.code for c in cities),
        len(poles),
        len(near),
        result.unique_m,
    )

    today = date.today()
    # The KMZ titles carry every city
    title_city = City(main.code, label, main.area, main.boundary_source)
    return RouteAnalysisData(
        code=f'{today.isoformat()}_{main.code}_multi_{PurePath(filename).stem}',
        analysis_date=today,
        city=label,
        ibge_code=main.code,
        routes_file=filename,
        poles_base=cities_label([lb for _, lb in by_city if lb], unique=True),
        radius_m=options.radius_m,
        city_poles=len(poles),
        near_poles=len(near),
        near_poles_pct=round(100 * len(near) / len(poles), 1),
        route_length_m=route_length_m,
        avg_span_m=round(
            (result.unique_m - result.no_pole_m) / len(near) if near else 0.0,
            1,
        ),
        poles_kmz=near_poles_kmz(title_city, poles, result, options.radius_m),
        all_poles_kmz=(
            cities_poles_kmz(label, cities, by_city)
            if options.export_all
            else None
        ),
        overlap_kmz=(
            overlap_kmz(f'Sobreposição - {label}', result.stretches)
            if options.overlap_kmz
            else None
        ),
        with_overlap_kmz=(
            with_overlap_kmz(
                f'Cabos com sobreposição - {label}',
                cables,
                length_with_overlap(cable_types),
            )
            if options.overlap_split_kmz
            else None
        ),
        without_overlap_kmz=(
            without_overlap_kmz(
                f'Cabos sem sobreposição - {label}',
                result.stretches,
                route_length_m,
            )
            if options.overlap_split_kmz
            else None
        ),
        cable_types=cable_types,
        cables=[cable_row(c, options.radius_m) for c in cables],
        cities=city_rows,
    )


def run_city_split_analysis(
    content: bytes, filename: str, options: RouteUploadOptions
) -> list[RouteAnalysisData]:
    """One analysis per city the routes pass through, each with only the
    stretch of the cables inside the city. Blocking: CPU and network.
    """
    cables = read_cables(content)
    if not cables:
        raise AnalysisError('Nenhuma linha encontrada no arquivo.')
    vertices = [p for c in cables for line in c.lines for p in line]
    cities = find_cities(vertices)
    by_city = cities_poles(cities, vertices)
    if not any(ps for ps, _ in by_city):
        utilities = ', '.join(b.utility for b in POLE_BASES)
        raise AnalysisError(
            f'Nenhum poste das bases ({utilities}) nos municípios das rotas '
            '(área de outra distribuidora?).'
        )

    analyses = []
    for city, (poles, poles_base) in zip(cities, by_city):
        city_cables = [
            Cable(c.folder, c.name, c.cable_type, lines)
            for c in cables
            if (lines := clip_lines(c.lines, city.area))
        ]
        if city_cables:
            analyses.append(
                city_analysis_data(
                    city, city_cables, (poles, poles_base), filename, options
                )
            )
    return analyses


def city_analysis_data(
    city: City,
    cables: list[Cable],
    found_poles: tuple[list[LonLat], str],
    filename: str,
    options: RouteUploadOptions,
) -> RouteAnalysisData:
    """The analysis of the cables of one city (already cut at its border);
    found_poles is (poles of the city, "Base de postes" label).
    """
    poles, poles_base = found_poles
    result = analyze(
        cables,
        poles,
        options.radius_m,
        with_stretches=options.overlap_kmz or options.overlap_split_kmz,
    )
    near = result.near_poles
    cable_types = cable_type_rows(cables, options.radius_m)
    route_length_m = round(result.unique_m)
    logger.info(
        'city split route analysis: city=%s poles=%d near=%d unique=%.0f',
        city.code,
        len(poles),
        len(near),
        result.unique_m,
    )

    today = date.today()
    return RouteAnalysisData(
        code=f'{today.isoformat()}_{city.code}_{PurePath(filename).stem}',
        analysis_date=today,
        city=city.name,
        ibge_code=city.code,
        routes_file=filename,
        poles_base=poles_base,
        radius_m=options.radius_m,
        city_poles=len(poles),
        near_poles=len(near),
        near_poles_pct=near_pct(len(near), len(poles)),
        route_length_m=route_length_m,
        avg_span_m=round(
            (result.unique_m - result.no_pole_m) / len(near) if near else 0.0,
            1,
        ),
        poles_kmz=near_poles_kmz(city, poles, result, options.radius_m),
        all_poles_kmz=(
            all_poles_kmz(city, poles) if options.export_all else None
        ),
        overlap_kmz=(
            overlap_kmz(f'Sobreposição - {city.name}', result.stretches)
            if options.overlap_kmz
            else None
        ),
        with_overlap_kmz=(
            with_overlap_kmz(
                f'Cabos com sobreposição - {city.name}',
                cables,
                length_with_overlap(cable_types),
            )
            if options.overlap_split_kmz
            else None
        ),
        without_overlap_kmz=(
            without_overlap_kmz(
                f'Cabos sem sobreposição - {city.name}',
                result.stretches,
                route_length_m,
            )
            if options.overlap_split_kmz
            else None
        ),
        cable_types=cable_types,
        cables=[cable_row(c, options.radius_m) for c in cables],
    )


def near_pct(near: int, total: int) -> float:
    return round(100 * near / total, 1) if total else 0.0


def clip_lines(lines: list[list[LonLat]], area) -> list[list[LonLat]]:
    """The parts of the lines inside the area, cut at its border."""
    clipped: list[list[LonLat]] = []
    for line in lines:
        current: list[LonLat] = []
        for a, b in zip(line, line[1:]):
            steps = max(1, math.ceil(math.dist(a, b) / CLIP_STEP))
            points = [
                (
                    a[0] + (b[0] - a[0]) * k / steps,
                    a[1] + (b[1] - a[1]) * k / steps,
                )
                for k in range(steps + 1)
            ]
            inside = [area.contains(*p) for p in points]
            if not current and inside[0]:
                current.append(a)
            for k in range(steps):
                p, q = points[k], points[k + 1]
                if inside[k] == inside[k + 1]:
                    continue
                cut = border_point(area, p, q, inside[k])
                if inside[k]:
                    current.append(cut)
                    if len(current) > 1:
                        clipped.append(current)
                    current = []
                else:
                    current = [cut]
            if inside[-1]:
                current.append(b)
        if len(current) > 1:
            clipped.append(current)
    # A line that only touches the border leaves a piece with no length
    return [line for line in clipped if len(set(line)) > 1]


def border_point(area, inside_end: LonLat, outside_end: LonLat, swap: bool):
    """Where the segment crosses the border, by bisection."""
    p, q = (inside_end, outside_end) if swap else (outside_end, inside_end)
    # p is inside, q is outside
    for _ in range(CLIP_BISECTIONS):
        mid = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
        if area.contains(*mid):
            p = mid
        else:
            q = mid
    return p


def city_near_rows(
    cities: list[City],
    by_city: list[tuple[list[LonLat], str]],
    near: list[int],
) -> list[CityIn]:
    """Total and near poles of each city; near holds indexes into the poles
    of every city, in the by_city order.
    """
    owner = [k for k, (ps, _) in enumerate(by_city) for _ in ps]
    near_by_city = Counter(owner[i] for i in near)
    return [
        CityIn(
            city=city.name,
            ibge_code=city.code,
            poles_base=label,
            city_poles=len(ps),
            near_poles=near_by_city[k],
            near_poles_pct=(
                round(100 * near_by_city[k] / len(ps), 1) if ps else 0.0
            ),
        )
        for k, (city, (ps, label)) in enumerate(zip(cities, by_city))
    ]


def cities_label(names: list[str], unique: bool = False) -> str:
    """'A + B + C', cut to fit the column: 'A + B (+3)'."""
    if unique:
        names = list(dict.fromkeys(names))
    for shown in range(len(names), 0, -1):
        rest = len(names) - shown
        text = ' + '.join(names[:shown]) + (f' (+{rest})' if rest else '')
        if len(text) <= LABEL_MAX:
            return text
    return names[0][:LABEL_MAX] if names else ''


def cities_poles(
    cities: list[City], vertices: list[LonLat]
) -> list[tuple[list[LonLat], str]]:
    """(poles inside the city from every base, "Base de postes" label) of
    each city; a pole on a border counts for the first city.
    """
    xs = [p[0] for p in vertices] + [
        x for c in cities for x in (c.area.bbox[0], c.area.bbox[2])
    ]
    ys = [p[1] for p in vertices] + [
        y for c in cities for y in (c.area.bbox[1], c.area.bbox[3])
    ]
    bbox = (
        min(xs) - BBOX_MARGIN,
        min(ys) - BBOX_MARGIN,
        max(xs) + BBOX_MARGIN,
        max(ys) + BBOX_MARGIN,
    )
    poles: list[list[LonLat]] = [[] for _ in cities]
    found: list[list[tuple]] = [[] for _ in cities]
    for base, path in local_bases():
        base_poles, manifest = read_poles(path, bbox)
        counts = [0] * len(cities)
        for pole in base_poles:
            for k, city in enumerate(cities):
                if city.area.contains(*pole):
                    poles[k].append(pole)
                    counts[k] += 1
                    break
        for k, count in enumerate(counts):
            if count:
                found[k].append((
                    count,
                    base.utility,
                    manifest.get('data_base'),
                ))
    return [
        (
            city_poles_,
            ' + '.join(
                ' '.join(filter(None, ('BDGD', utility, data_base)))
                for count, utility, data_base in city_found
                if count >= BASE_MIN_SHARE * len(city_poles_)
            ),
        )
        for city_poles_, city_found in zip(poles, found)
    ]


def cities_poles_kmz(
    label: str,
    cities: list[City],
    by_city: list[tuple[list[LonLat], str]],
) -> bytes:
    """Every pole of the cities, one folder per city."""
    return points_kmz(
        f'Postes - {label}',
        [
            (city.name, 'ffffffff', [(lon, lat, '') for lon, lat in ps])
            for city, (ps, _) in zip(cities, by_city)
            if ps
        ],
    )


def length_with_overlap(cable_types: list[CableTypeIn]) -> int:
    """Every cable's full length: the sum of "Metros" in "Por tipo"."""
    return sum(row.length_m for row in cable_types)


def city_poles(city: City, vertices: list[LonLat]) -> tuple[list[LonLat], str]:
    """(poles inside the city from every base, "Base de postes" label)."""
    xs, ys = [p[0] for p in vertices], [p[1] for p in vertices]
    cx0, cy0, cx1, cy1 = city.area.bbox
    bbox = (
        min(cx0, *xs) - BBOX_MARGIN,
        min(cy0, *ys) - BBOX_MARGIN,
        max(cx1, *xs) + BBOX_MARGIN,
        max(cy1, *ys) + BBOX_MARGIN,
    )
    # A city on a border may have more than one utility
    poles, found = [], []
    for base, path in local_bases():
        base_poles, manifest = read_poles(path, bbox)
        inside = [p for p in base_poles if city.area.contains(*p)]
        if inside:
            poles += inside
            found.append((
                len(inside),
                base.utility,
                manifest.get('data_base'),
            ))
    if not poles:
        utilities = ', '.join(b.utility for b in POLE_BASES)
        raise AnalysisError(
            f'Nenhum poste das bases ({utilities}) neste município '
            '(área de outra distribuidora?).'
        )
    label = ' + '.join(
        ' '.join(filter(None, ('BDGD', utility, data_base)))
        for count, utility, data_base in found
        if count >= BASE_MIN_SHARE * len(poles)
    )
    return poles, label


def near_poles_kmz(
    city: City, poles: list[LonLat], result: RouteResult, radius_m: float
) -> bytes:
    close_m = min(CLOSE_POLE_M, radius_m)
    distance = result.min_distance

    def points(indexes: list[int]):
        return [(*poles[i], f'{distance[i]:.1f} m do cabo') for i in indexes]

    close = [i for i in result.near_poles if distance[i] <= close_m]
    far = [i for i in result.near_poles if distance[i] > close_m]
    groups = [(f'Até {close_m:g} m do cabo', 'ff00ff00', points(close))]
    if far:
        groups.append((
            f'De {close_m:g} a {radius_m:g} m do cabo',
            'ff00ffff',
            points(far),
        ))
    return points_kmz(f'Postes utilizados - {city.name}', groups)


def all_poles_kmz(city: City, poles: list[LonLat]) -> bytes:
    return points_kmz(
        f'Postes - {city.name}',
        [
            (
                'Postes do município',
                'ffffffff',
                [(lon, lat, '') for lon, lat in poles],
            )
        ],
    )


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


async def save_analysis(
    session: AsyncSession, data: RouteAnalysisData
) -> RouteAnalysis:
    # Re-sending the same analysis replaces it, so a retry never duplicates
    await session.execute(
        delete(RouteAnalysis).where(RouteAnalysis.code == data.code)
    )
    # model_dump() of a RouteAnalysisCreate would base64-encode the KMZ
    # again; the attributes hold the decoded bytes
    kmz = {kind.column.key: getattr(data, kind.column.key) for kind in KmzKind}
    analysis = RouteAnalysis(
        **data.model_dump(exclude={'cable_types', 'cables', 'cities', *kmz}),
        **kmz,
        cable_types=[
            RouteCableType(**item.model_dump()) for item in data.cable_types
        ],
        cables=[RouteCable(**item.model_dump()) for item in data.cables],
        cities=[
            RouteAnalysisCity(**item.model_dump()) for item in data.cities
        ],
    )
    session.add(analysis)
    await session.commit()
    return analysis


async def save_city_analyses(
    session: AsyncSession, analyses: list[RouteAnalysisData]
) -> list[tuple[RouteAnalysis, bool]]:
    """(analysis, merged) of each city: summed into the latest analysis of
    the city when there is one, else stored as a new analysis.
    """
    saved = []
    for data in analyses:
        existing = await session.scalar(
            select(RouteAnalysis)
            .where(RouteAnalysis.ibge_code == data.ibge_code)
            .order_by(
                RouteAnalysis.analysis_date.desc(),
                RouteAnalysis.created_at.desc(),
            )
            .limit(1)
            .options(
                selectinload(RouteAnalysis.cable_types),
                selectinload(RouteAnalysis.cables),
            )
        )
        if existing is None:
            saved.append((await save_analysis(session, data), False))
        else:
            merge_analysis(existing, data)
            await session.commit()
            saved.append((existing, True))
    return saved


def merge_analysis(analysis: RouteAnalysis, data: RouteAnalysisData) -> None:
    """Adds the lengths, near poles, cable types and cables of data to the
    analysis. The average span and the KMZ files are kept as they are.
    """
    analysis.routes_file = cities_label(
        [*analysis.routes_file.split(' + '), data.routes_file], unique=True
    )[:255]
    analysis.city_poles = max(analysis.city_poles, data.city_poles)
    analysis.near_poles += data.near_poles
    analysis.near_poles_pct = min(
        100.0, near_pct(analysis.near_poles, analysis.city_poles)
    )
    analysis.route_length_m += data.route_length_m

    by_type = {row.cable_type: row for row in analysis.cable_types}
    for item in data.cable_types:
        row = by_type.get(item.cable_type)
        if row is None:
            analysis.cable_types.append(RouteCableType(**item.model_dump()))
            continue
        row.cables += item.cables
        row.length_m += item.length_m
        row.near_poles += item.near_poles
        row.unique_length_m = (row.unique_length_m or 0) + item.unique_length_m
    analysis.cables.extend(
        RouteCable(**item.model_dump()) for item in data.cables
    )


def analysis_ref_condition(analysis_ref: str) -> ColumnElement[bool]:
    """An analysis is referenced by id (UUID) or by code ("ID análise")."""
    try:
        return RouteAnalysis.id == UUID(analysis_ref)
    except ValueError:
        return RouteAnalysis.code == analysis_ref


# (analysis, the KMZ files it has), without loading the KMZ bytes
AnalysisRow = tuple[RouteAnalysis, frozenset[KmzKind]]
OPTIONAL_KMZ = tuple(kind for kind in KmzKind if kind != KmzKind.POLES)


def analysis_query() -> Select:
    return select(
        RouteAnalysis, *(kind.column.is_not(None) for kind in OPTIONAL_KMZ)
    )


def to_analysis_row(row) -> AnalysisRow:
    analysis, *has_kmz = row
    kinds = {KmzKind.POLES}
    kinds.update(kind for kind, has in zip(OPTIONAL_KMZ, has_kmz) if has)
    return analysis, frozenset(kinds)


async def list_analyses(
    session: AsyncSession, ibge_code: str | None
) -> list[AnalysisRow]:
    query = analysis_query().order_by(
        RouteAnalysis.analysis_date, RouteAnalysis.code
    )
    if ibge_code:
        query = query.where(RouteAnalysis.ibge_code == ibge_code)
    return [to_analysis_row(row) for row in (await session.execute(query))]


async def get_analysis(
    session: AsyncSession, analysis_ref: str, with_rows: bool = False
) -> AnalysisRow | None:
    query = analysis_query().where(analysis_ref_condition(analysis_ref))
    if with_rows:
        query = query.options(
            selectinload(RouteAnalysis.cable_types),
            selectinload(RouteAnalysis.cables),
            selectinload(RouteAnalysis.cities),
        )
    row = (await session.execute(query)).first()
    return to_analysis_row(row) if row else None


async def update_analysis(
    session: AsyncSession, analysis_ref: str, changes: dict
) -> AnalysisRow | None:
    row = await get_analysis(session, analysis_ref)
    if row is None:
        return None
    analysis, kmz_kinds = row
    for field, value in changes.items():
        setattr(analysis, field, value)
    await session.commit()
    # updated_at is set by the database
    await session.refresh(analysis)
    return analysis, kmz_kinds


async def update_row[T: (RouteCableType, RouteCable)](
    session: AsyncSession, model: type[T], row_id: UUID, changes: dict
) -> T | None:
    row = await session.get(model, row_id)
    if row is None:
        return None
    for field, value in changes.items():
        setattr(row, field, value)
    await session.commit()
    await session.refresh(row)
    return row


async def delete_analysis(session: AsyncSession, analysis_ref: str) -> bool:
    """The cable types, cables and KMZ go with it (ON DELETE CASCADE)."""
    deleted_id = await session.scalar(
        delete(RouteAnalysis)
        .where(analysis_ref_condition(analysis_ref))
        .returning(RouteAnalysis.id)
    )
    await session.commit()
    return deleted_id is not None


async def summary_csv(
    session: AsyncSession, ibge_code: str | None, kmz_link: KmzLink
) -> str:
    rows = [
        [
            analysis.code,
            analysis.analysis_date.isoformat(),
            analysis.city,
            analysis.ibge_code,
            analysis.routes_file,
            analysis.poles_base,
            analysis.radius_m,
            analysis.city_poles,
            analysis.near_poles,
            analysis.near_poles_pct,
            analysis.route_length_m,
            analysis.avg_span_m,
            *(
                kmz_link(analysis.id, kind) if kind in kmz_kinds else ''
                for kind in KmzKind
            ),
        ]
        for analysis, kmz_kinds in await list_analyses(session, ibge_code)
    ]
    return to_csv(SUMMARY_HEADER, rows)


async def cable_types_csv(session: AsyncSession, ibge_code: str | None) -> str:
    query = (
        select(
            RouteAnalysis.code,
            RouteAnalysis.analysis_date,
            RouteAnalysis.city,
            RouteAnalysis.routes_file,
            RouteCableType.cable_type,
            RouteCableType.cables,
            RouteCableType.length_m,
            RouteCableType.near_poles,
            RouteCableType.unique_length_m,
        )
        .join(RouteAnalysis, RouteCableType.analysis_id == RouteAnalysis.id)
        .order_by(
            RouteAnalysis.analysis_date,
            RouteAnalysis.code,
            RouteCableType.cable_type,
        )
    )
    if ibge_code:
        query = query.where(RouteAnalysis.ibge_code == ibge_code)

    rows = [list(row) for row in (await session.execute(query)).all()]
    return to_csv(CABLE_TYPES_HEADER, rows)


async def cables_csv(session: AsyncSession, ibge_code: str | None) -> str:
    query = (
        select(
            RouteAnalysis.code,
            RouteCable.folder,
            RouteCable.name,
            RouteCable.cable_type,
            RouteCable.length_m,
            RouteCable.near_poles,
            RouteCable.near_poles_5m,
            RouteCable.no_pole_m,
            RouteCable.unique_length_m,
        )
        .join(RouteAnalysis, RouteCable.analysis_id == RouteAnalysis.id)
        .order_by(
            RouteAnalysis.analysis_date,
            RouteAnalysis.code,
            RouteCable.folder,
            RouteCable.name,
        )
    )
    if ibge_code:
        query = query.where(RouteAnalysis.ibge_code == ibge_code)

    rows = [list(row) for row in (await session.execute(query)).all()]
    return to_csv(CABLES_HEADER, rows)


async def load_kmz(
    session: AsyncSession, analysis_id: UUID, kind: KmzKind
) -> tuple[str, bytes] | None:
    row = (
        await session.execute(
            select(RouteAnalysis.code, kind.column).where(
                RouteAnalysis.id == analysis_id
            )
        )
    ).first()
    if row is None or row[1] is None:
        return None
    return row[0], row[1]


def to_csv(header: list[str], rows: list[list]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue()
