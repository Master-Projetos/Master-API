from typing import NamedTuple
from uuid import UUID

from sqlalchemy import ColumnElement, Select, and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.route_poles.analysis.kmz import KmzKind
from app.modules.route_poles.model import (
    Backbone,
    BackboneCable,
    BackboneCableType,
    BackboneCity,
    StoredKmz,
    kmz_kinds,
    ref_condition,
)
from app.modules.route_poles.schemas import BackboneData, BackboneSearch


class BackboneRow(NamedTuple):
    backbone: Backbone
    # By city id
    kmz_kinds: dict[UUID, frozenset[KmzKind]]


def contains(column, text: str) -> ColumnElement[bool]:
    escaped = (
        text.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    )
    return column.ilike(f'%{escaped}%', escape='\\')


async def save_backbone(
    session: AsyncSession, data: BackboneData
) -> BackboneRow:
    # Sending the same backbone again replaces it, so a retry never duplicates
    await session.execute(delete(Backbone).where(Backbone.code == data.code))
    backbone = Backbone(
        code=data.code,
        backbone_date=data.backbone_date,
        routes_file=data.routes_file,
        radius_m=data.radius_m,
        cities=[
            BackboneCity(
                **city.columns(),
                cable_types=[
                    BackboneCableType(**row.model_dump())
                    for row in city.cable_types
                ],
                cables=[
                    BackboneCable(**row.model_dump()) for row in city.cables
                ],
            )
            for city in data.cities
        ],
    )
    session.add(backbone)
    await session.commit()
    # Loaded again for the server defaults and for which KMZ files it has
    session.expunge(backbone)
    query = select(Backbone).where(Backbone.id == backbone.id)
    return (await load_rows(session, query))[0]


async def list_backbones(
    session: AsyncSession, search: BackboneSearch
) -> list[BackboneRow]:
    query = (
        select(Backbone)
        .order_by(Backbone.backbone_date.desc(), Backbone.code)
        .limit(search.limit)
        .offset(search.offset)
    )
    if search.routes_file:
        query = query.where(contains(Backbone.routes_file, search.routes_file))
    if search.date_from:
        query = query.where(Backbone.backbone_date >= search.date_from)
    if search.date_to:
        query = query.where(Backbone.backbone_date <= search.date_to)
    city_conditions = []
    if search.ibge_code:
        city_conditions.append(BackboneCity.ibge_code == search.ibge_code)
    if search.city:
        city_conditions.append(contains(BackboneCity.city, search.city))
    if city_conditions:
        query = query.where(Backbone.cities.any(and_(*city_conditions)))
    return await load_rows(session, query)


async def get_backbone(
    session: AsyncSession, ref: str, with_rows: bool = False
) -> BackboneRow | None:
    query = select(Backbone).where(ref_condition(Backbone, ref))
    rows = await load_rows(session, query, with_rows)
    return rows[0] if rows else None


async def delete_backbone(session: AsyncSession, ref: str) -> bool:
    """The cities, their cable types, cables and KMZ go with it (ON DELETE
    CASCADE).
    """
    deleted_id = await session.scalar(
        delete(Backbone)
        .where(ref_condition(Backbone, ref))
        .returning(Backbone.id)
    )
    await session.commit()
    return deleted_id is not None


async def load_city_kmz(
    session: AsyncSession, city_id: UUID, kind: KmzKind
) -> StoredKmz | None:
    row = (
        await session.execute(
            select(
                Backbone.code,
                BackboneCity.ibge_code,
                getattr(BackboneCity, kind.attr),
            )
            .join(Backbone, BackboneCity.backbone_id == Backbone.id)
            .where(BackboneCity.id == city_id)
        )
    ).first()
    if row is None or row[2] is None:
        return None
    code, ibge_code, content = row
    return StoredKmz(f'{code}_{ibge_code}', content)


async def load_rows(
    session: AsyncSession, query: Select, with_rows: bool = False
) -> list[BackboneRow]:
    cities = selectinload(Backbone.cities)
    if with_rows:
        cities = cities.options(
            selectinload(BackboneCity.cable_types),
            selectinload(BackboneCity.cables),
        )
    backbones = (await session.scalars(query.options(cities))).all()
    kinds = await city_kmz_kinds(session, [b.id for b in backbones])
    return [
        BackboneRow(b, {city.id: kinds[city.id] for city in b.cities})
        for b in backbones
    ]


async def city_kmz_kinds(
    session: AsyncSession, backbone_ids: list[UUID]
) -> dict[UUID, frozenset[KmzKind]]:
    query = select(BackboneCity.id, *BackboneCity.kmz_flags()).where(
        BackboneCity.backbone_id.in_(backbone_ids)
    )
    return {
        city_id: kmz_kinds(flags)
        for city_id, *flags in await session.execute(query)
    }
