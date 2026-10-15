import csv
import io
import logging
import re
from collections import defaultdict
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
    RouteAnalysisData,
    RouteUploadOptions,
)
from app.modules.route_poles.analysis.city import City, find_city
from app.modules.route_poles.analysis.engine import RouteResult, analyze
from app.modules.route_poles.analysis.errors import AnalysisError, SourceError
from app.modules.route_poles.analysis.kmz import overlap_kmz, points_kmz
from app.modules.route_poles.analysis.pole_base import (
    POLE_BASES,
    local_bases,
    read_poles,
)
from app.modules.route_poles.analysis.routes import Cable, read_cables
from app.modules.route_poles.model import (
    KmzKind,
    RouteAnalysis,
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
# Share of the city's poles a utility needs to be named in "Base de postes":
# every pole counts, but a network that only crosses the city border is not
# named (e.g. 31 Cemig-D poles in Campos do Jordão, an Elektro city)
BASE_MIN_SHARE = 0.05
# The poles KMZ splits the near poles at this distance (m)
CLOSE_POLE_M = 5.0
FIRST_NUMBER = re.compile(r'\d+')


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
        cables, poles, options.radius_m, with_stretches=options.overlap_kmz
    )
    near = result.near_poles
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
        route_length_m=round(result.unique_m),
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
        cable_types=cable_type_rows(cables, options.radius_m),
        cables=[cable_row(c, options.radius_m) for c in cables],
    )


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
    analysis = RouteAnalysis(
        # model_dump() of a RouteAnalysisCreate would base64-encode the KMZ
        # again; the attributes hold the decoded bytes
        **data.model_dump(
            exclude={
                'cable_types',
                'cables',
                'poles_kmz',
                'all_poles_kmz',
                'overlap_kmz',
            }
        ),
        poles_kmz=data.poles_kmz,
        all_poles_kmz=data.all_poles_kmz,
        overlap_kmz=data.overlap_kmz,
        cable_types=[
            RouteCableType(**item.model_dump()) for item in data.cable_types
        ],
        cables=[RouteCable(**item.model_dump()) for item in data.cables],
    )
    session.add(analysis)
    await session.commit()
    return analysis


def analysis_ref_condition(analysis_ref: str) -> ColumnElement[bool]:
    """An analysis is referenced by id (UUID) or by code ("ID análise")."""
    try:
        return RouteAnalysis.id == UUID(analysis_ref)
    except ValueError:
        return RouteAnalysis.code == analysis_ref


# (analysis, the KMZ files it has), without loading the KMZ bytes
AnalysisRow = tuple[RouteAnalysis, frozenset[KmzKind]]
OPTIONAL_KMZ = (KmzKind.ALL_POLES, KmzKind.OVERLAP)


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
