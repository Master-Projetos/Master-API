from typing import NamedTuple
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.route_poles.analysis.kmz import KmzKind
from app.modules.route_poles.model import (
    RouteAnalysis,
    RouteCable,
    RouteCableType,
    StoredKmz,
    kmz_kinds,
    ref_condition,
)
from app.modules.route_poles.schemas import RouteAnalysisData


class AnalysisRow(NamedTuple):
    analysis: RouteAnalysis
    kmz_kinds: frozenset[KmzKind]


def to_row(row) -> AnalysisRow:
    analysis, *flags = row
    return AnalysisRow(analysis, kmz_kinds(flags))


async def save_analysis(
    session: AsyncSession, data: RouteAnalysisData
) -> RouteAnalysis:
    # Sending the same analysis again replaces it, so a retry never duplicates
    await session.execute(
        delete(RouteAnalysis).where(RouteAnalysis.code == data.code)
    )
    analysis = RouteAnalysis(
        **data.columns(),
        cable_types=[
            RouteCableType(**row.model_dump()) for row in data.cable_types
        ],
        cables=[RouteCable(**row.model_dump()) for row in data.cables],
    )
    session.add(analysis)
    await session.commit()
    return analysis


async def list_analyses(
    session: AsyncSession, ibge_code: str | None
) -> list[AnalysisRow]:
    query = RouteAnalysis.select_with_kmz_kinds().order_by(
        RouteAnalysis.analysis_date, RouteAnalysis.code
    )
    if ibge_code:
        query = query.where(RouteAnalysis.ibge_code == ibge_code)
    return [to_row(row) for row in await session.execute(query)]


async def get_analysis(
    session: AsyncSession, ref: str, with_rows: bool = False
) -> AnalysisRow | None:
    query = RouteAnalysis.select_with_kmz_kinds().where(
        ref_condition(RouteAnalysis, ref)
    )
    if with_rows:
        query = query.options(
            selectinload(RouteAnalysis.cable_types),
            selectinload(RouteAnalysis.cables),
        )
    row = (await session.execute(query)).first()
    return to_row(row) if row else None


async def delete_analysis(session: AsyncSession, ref: str) -> bool:
    """The cable types, cables and KMZ go with it (ON DELETE CASCADE)."""
    deleted_id = await session.scalar(
        delete(RouteAnalysis)
        .where(ref_condition(RouteAnalysis, ref))
        .returning(RouteAnalysis.id)
    )
    await session.commit()
    return deleted_id is not None


async def load_kmz(
    session: AsyncSession, analysis_id: UUID, kind: KmzKind
) -> StoredKmz | None:
    row = (
        await session.execute(
            select(
                RouteAnalysis.code, getattr(RouteAnalysis, kind.attr)
            ).where(RouteAnalysis.id == analysis_id)
        )
    ).first()
    if row is None or row[1] is None:
        return None
    return StoredKmz(*row)
