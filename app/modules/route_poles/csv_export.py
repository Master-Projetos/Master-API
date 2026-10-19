"""The CSVs read by Google Sheets (IMPORTDATA). Headers are in Portuguese
because they become the sheet columns; new columns go at the end, so the
formulas of the sheet keep their references.
"""

import csv
import io
from collections.abc import Callable
from enum import StrEnum
from operator import attrgetter
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.route_poles.analysis.kmz import KmzKind
from app.modules.route_poles.analysis_service import list_analyses
from app.modules.route_poles.model import (
    RouteAnalysis,
    RouteCable,
    RouteCableType,
)

KmzLink = Callable[[UUID, KmzKind], str]


class CsvTable(StrEnum):
    SUMMARY = 'summary'
    CABLE_TYPES = 'cable-types'
    CABLES = 'cables'


SUMMARY_COLUMNS = [
    ('ID análise', 'code'),
    ('Data', 'analysis_date'),
    ('Município', 'city'),
    ('Código IBGE', 'ibge_code'),
    ('Arquivo de rotas', 'routes_file'),
    ('Base de postes', 'poles_base'),
    ('Raio (m)', 'radius_m'),
    ('Postes totais no município', 'city_poles'),
    ('Postes próximos aos cabos', 'near_poles'),
    ('% dos postes da cidade', 'near_poles_pct'),
    ('Metragem total sem sobreposição (m)', 'route_length_m'),
    ('Vão médio estimado (m)', 'avg_span_m'),
]
SUMMARY_KMZ_HEADERS = {
    KmzKind.POLES: 'KMZ postes utilizados',
    KmzKind.ALL_POLES: 'KMZ todos os postes',
    KmzKind.OVERLAP: 'KMZ sobreposição',
    KmzKind.WITH_OVERLAP: 'KMZ com sobreposição',
    KmzKind.WITHOUT_OVERLAP: 'KMZ sem sobreposição',
}
CABLE_TYPE_COLUMNS = [
    ('ID análise', RouteAnalysis.code),
    ('Data', RouteAnalysis.analysis_date),
    ('Município', RouteAnalysis.city),
    ('Arquivo de rotas', RouteAnalysis.routes_file),
    ('Tipo de cabo', RouteCableType.cable_type),
    ('Cabos', RouteCableType.cables),
    ('Metros', RouteCableType.length_m),
    ('Postes próximos', RouteCableType.near_poles),
    ('Metros sem sobreposição', RouteCableType.unique_length_m),
]
CABLE_COLUMNS = [
    ('ID análise', RouteAnalysis.code),
    ('Pasta', RouteCable.folder),
    ('Cabo', RouteCable.name),
    ('Tipo de cabo', RouteCable.cable_type),
    ('Metros', RouteCable.length_m),
    ('Postes no raio', RouteCable.near_poles),
    ('Postes a até 5 m', RouteCable.near_poles_5m),
    ('Trecho sem poste a <25 m (m)', RouteCable.no_pole_m),
    ('Metros sem sobreposição', RouteCable.unique_length_m),
]


async def export_csv(
    session: AsyncSession,
    table: CsvTable,
    ibge_code: str | None,
    kmz_link: KmzLink,
) -> str:
    match table:
        case CsvTable.SUMMARY:
            return await summary_csv(session, ibge_code, kmz_link)
        case CsvTable.CABLE_TYPES:
            return await cable_types_csv(session, ibge_code)
        case CsvTable.CABLES:
            return await cables_csv(session, ibge_code)


async def summary_csv(
    session: AsyncSession, ibge_code: str | None, kmz_link: KmzLink
) -> str:
    getters = [attrgetter(attr) for _, attr in SUMMARY_COLUMNS]
    rows = [
        [
            *(get(analysis) for get in getters),
            *(
                kmz_link(analysis.id, kind) if kind in kmz_kinds else ''
                for kind in KmzKind
            ),
        ]
        for analysis, kmz_kinds in await list_analyses(session, ibge_code)
    ]
    header = [name for name, _ in SUMMARY_COLUMNS] + [
        SUMMARY_KMZ_HEADERS[kind] for kind in KmzKind
    ]
    return to_csv(header, rows)


async def cable_types_csv(session: AsyncSession, ibge_code: str | None) -> str:
    query = (
        select(*(column for _, column in CABLE_TYPE_COLUMNS))
        .join(RouteAnalysis, RouteCableType.analysis_id == RouteAnalysis.id)
        .order_by(
            RouteAnalysis.analysis_date,
            RouteAnalysis.code,
            RouteCableType.cable_type,
        )
    )
    return await query_csv(session, query, CABLE_TYPE_COLUMNS, ibge_code)


async def cables_csv(session: AsyncSession, ibge_code: str | None) -> str:
    query = (
        select(*(column for _, column in CABLE_COLUMNS))
        .join(RouteAnalysis, RouteCable.analysis_id == RouteAnalysis.id)
        .order_by(
            RouteAnalysis.analysis_date,
            RouteAnalysis.code,
            RouteCable.folder,
            RouteCable.name,
        )
    )
    return await query_csv(session, query, CABLE_COLUMNS, ibge_code)


async def query_csv(session, query, columns, ibge_code: str | None) -> str:
    if ibge_code:
        query = query.where(RouteAnalysis.ibge_code == ibge_code)
    rows = [list(row) for row in await session.execute(query)]
    return to_csv([name for name, _ in columns], rows)


def to_csv(header: list[str], rows: list[list]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue()
