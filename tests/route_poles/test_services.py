import pytest
from sqlalchemy import func, select

from app.modules.route_poles import analysis_service, backbone_service
from app.modules.route_poles.analysis.kmz import KmzKind
from app.modules.route_poles.csv_export import (
    cable_types_csv,
    cables_csv,
    summary_csv,
)
from app.modules.route_poles.model import (
    BackboneCable,
    BackboneCableType,
    BackboneCity,
    RouteCable,
    RouteCableType,
)
from app.modules.route_poles.schemas import BackboneSearch
from tests.route_poles.golden_support import load_golden, normalize

pytestmark = pytest.mark.anyio

ALL_KINDS = frozenset(KmzKind)


async def count(session, model) -> int:
    return await session.scalar(select(func.count()).select_from(model))


def link(analysis_id, kind) -> str:
    return f'link/{kind.value}'


async def test_save_analysis_replaces_the_same_code(session, analysis_data):
    await analysis_service.save_analysis(session, analysis_data)
    changed = analysis_data.model_copy(update={'near_poles': 1})
    await analysis_service.save_analysis(session, changed)

    rows = await analysis_service.list_analyses(session, None)
    assert [row.analysis.near_poles for row in rows] == [1]
    assert await count(session, RouteCable) == len(analysis_data.cables)
    assert await count(session, RouteCableType) == len(
        analysis_data.cable_types
    )


async def test_analysis_rows_know_which_kmz_files_exist(
    session, analysis_data, plain_analysis_data
):
    await analysis_service.save_analysis(session, analysis_data)
    await analysis_service.save_analysis(session, plain_analysis_data)

    by_file = {
        row.analysis.routes_file: row.kmz_kinds
        for row in await analysis_service.list_analyses(session, None)
    }
    assert by_file['backbone_bh.kmz'] == ALL_KINDS
    assert by_file['plain.kmz'] == {KmzKind.POLES}


async def test_get_analysis_by_id_or_code_with_its_rows(
    session, analysis_data
):
    saved = await analysis_service.save_analysis(session, analysis_data)
    session.expunge_all()

    by_code = await analysis_service.get_analysis(
        session, saved.code, with_rows=True
    )
    by_id = await analysis_service.get_analysis(session, str(saved.id))
    assert by_code.analysis.id == by_id.analysis.id == saved.id
    assert len(by_code.analysis.cables) == len(analysis_data.cables)
    assert await analysis_service.get_analysis(session, 'missing') is None


async def test_delete_analysis(session, analysis_data):
    saved = await analysis_service.save_analysis(session, analysis_data)

    assert await analysis_service.delete_analysis(session, str(saved.id))
    assert not await analysis_service.delete_analysis(session, saved.code)
    assert await count(session, RouteCable) == 0


async def test_load_kmz_returns_only_files_that_exist(
    session, analysis_data, plain_analysis_data
):
    full = await analysis_service.save_analysis(session, analysis_data)
    plain = await analysis_service.save_analysis(session, plain_analysis_data)

    kmz = await analysis_service.load_kmz(session, full.id, KmzKind.OVERLAP)
    assert kmz.name == full.code
    assert kmz.content == analysis_data.overlap_kmz
    assert (
        await analysis_service.load_kmz(session, plain.id, KmzKind.OVERLAP)
        is None
    )


async def test_csvs_match_golden(session, analysis_data):
    await analysis_service.save_analysis(session, analysis_data)
    csvs = {
        'summary': await summary_csv(session, None, link),
        'summary_filtered': await summary_csv(session, '1', link),
        'cable_types': await cable_types_csv(session, None),
        'cables': await cables_csv(session, '3122306'),
    }
    assert normalize(csvs) == load_golden('csv')


async def test_save_backbone_stores_every_city(session, backbone_data):
    row = await backbone_service.save_backbone(session, backbone_data)

    assert row.backbone.code == backbone_data.code
    assert [c.ibge_code for c in row.backbone.cities] == [
        '3122306',
        '3132404',
    ]
    assert all(kinds == ALL_KINDS for kinds in row.kmz_kinds.values())
    # Server defaults come with the reload
    assert row.backbone.created_at is not None
    assert await count(session, BackboneCableType) == sum(
        len(c.cable_types) for c in backbone_data.cities
    )
    assert await count(session, BackboneCable) == sum(
        len(c.cables) for c in backbone_data.cities
    )


async def test_save_backbone_replaces_the_same_code(session, backbone_data):
    await backbone_service.save_backbone(session, backbone_data)
    await backbone_service.save_backbone(session, backbone_data)

    rows = await backbone_service.list_backbones(session, BackboneSearch())
    assert len(rows) == 1
    assert await count(session, BackboneCity) == len(backbone_data.cities)
    assert await count(session, BackboneCable) == sum(
        len(c.cables) for c in backbone_data.cities
    )


async def test_get_backbone_by_id_or_code(session, backbone_data):
    saved = await backbone_service.save_backbone(session, backbone_data)
    session.expunge_all()

    by_code = await backbone_service.get_backbone(
        session, saved.backbone.code, with_rows=True
    )
    by_id = await backbone_service.get_backbone(
        session, str(saved.backbone.id)
    )
    assert by_code.backbone.id == by_id.backbone.id
    assert all(city.cables for city in by_code.backbone.cities)
    assert await backbone_service.get_backbone(session, 'missing') is None


async def test_delete_backbone_removes_everything_under_it(
    session, backbone_data
):
    saved = await backbone_service.save_backbone(session, backbone_data)

    assert await backbone_service.delete_backbone(
        session, str(saved.backbone.id)
    )
    assert not await backbone_service.delete_backbone(
        session, saved.backbone.code
    )
    for model in (BackboneCity, BackboneCableType, BackboneCable):
        assert await count(session, model) == 0


@pytest.mark.parametrize(
    ('search', 'expected'),
    [
        ({}, 2),
        ({'ibge_code': '3132404'}, 2),
        ({'ibge_code': '9999999'}, 0),
        ({'city': 'divin'}, 2),
        ({'city': 'itaú'}, 2),
        ({'city': '%'}, 0),
        ({'city': '_'}, 0),
        ({'ibge_code': '3132404', 'city': 'divin'}, 0),
        ({'routes_file': 'plain'}, 1),
        ({'routes_file': 'BACKBONE_BH'}, 1),
        ({'date_from': '2000-01-01'}, 2),
        ({'date_from': '2999-01-01'}, 0),
        ({'date_to': '2000-01-01'}, 0),
        ({'limit': 1}, 1),
        ({'limit': 1, 'offset': 1}, 1),
        ({'limit': 1, 'offset': 2}, 0),
    ],
)
async def test_search_backbones(
    session, backbone_data, plain_backbone_data, search, expected
):
    await backbone_service.save_backbone(session, backbone_data)
    await backbone_service.save_backbone(session, plain_backbone_data)

    rows = await backbone_service.list_backbones(
        session, BackboneSearch(**search)
    )
    assert len(rows) == expected


async def test_search_lists_every_city_of_a_matching_backbone(
    session, backbone_data
):
    await backbone_service.save_backbone(session, backbone_data)

    (row,) = await backbone_service.list_backbones(
        session, BackboneSearch(ibge_code='3132404')
    )
    assert len(row.backbone.cities) == len(backbone_data.cities)


async def test_load_city_kmz(session, backbone_data, plain_backbone_data):
    full = await backbone_service.save_backbone(session, backbone_data)
    plain = await backbone_service.save_backbone(session, plain_backbone_data)
    full_city = full.backbone.cities[1]
    plain_city = plain.backbone.cities[1]

    kmz = await backbone_service.load_city_kmz(
        session, full_city.id, KmzKind.WITH_OVERLAP
    )
    assert kmz.name == f'{full.backbone.code}_{full_city.ibge_code}'
    assert kmz.content == backbone_data.cities[1].with_overlap_kmz
    assert (
        await backbone_service.load_city_kmz(
            session, plain_city.id, KmzKind.WITH_OVERLAP
        )
        is None
    )
