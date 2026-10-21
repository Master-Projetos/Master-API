"""The licensed poles crossed with the poles in use."""

import io
import zipfile
from datetime import date, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.route_poles import (
    analysis_service,
    backbone_service,
    licensed_service,
)
from app.modules.route_poles.analysis import pipeline
from app.modules.route_poles.analysis.errors import AnalysisError, SourceError
from app.modules.route_poles.analysis.kmz import all_poles_kmz
from app.modules.route_poles.analysis.licensing import (
    assign_markers,
    cables_near,
    compare_city,
    comparison_kmz,
    decode_cable_lines,
    encode_cable_lines,
    poles_near,
)
from app.modules.route_poles.analysis.routes import Cable, read_markers
from app.modules.route_poles.constants import MATCH_TOLERANCE_M
from tests.route_poles import scenarios as sc

pytestmark = pytest.mark.anyio

# About one meter of latitude
ONE_M = 0.000009
LON, LAT = -44.89, -20.135


def pole(index: int, north_m: float = 0.0) -> tuple[float, float]:
    """Poles 100 m apart, so only the same index can match."""
    return (LON + index * 0.001, LAT + north_m * ONE_M)


def test_read_markers_reads_points_wherever_they_are():
    kml = (
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        '<Folder><Placemark><name>P1</name><Point><coordinates>-44.1,-20.2,0'
        '</coordinates></Point></Placemark></Folder>'
        '<Placemark><description>only a description</description>'
        '<MultiGeometry><Point><coordinates>-44.3,-20.4</coordinates></Point>'
        '</MultiGeometry></Placemark>'
        '<Placemark><name>a cable</name><LineString><coordinates>'
        '-44.1,-20.1,0 -44.2,-20.2,0</coordinates></LineString></Placemark>'
        '</Document></kml>'
    ).encode()

    assert read_markers(kml) == [
        (-44.1, -20.2, 'P1'),
        (-44.3, -20.4, 'only a description'),
    ]


def test_read_markers_reads_a_kmz_and_ignores_the_cables():
    markers = [(-44.1, -20.2, 'a'), (-44.3, -20.4, 'b')]

    assert read_markers(sc.markers_kmz(markers)) == markers
    # The routes file has one marker among its cables
    assert read_markers(sc.routes_kmz()) == [(-44.89, -20.14, 'Marker')]


def test_read_markers_rejects_bad_coordinates_and_bad_files():
    bad = (
        b'<kml><Placemark><Point><coordinates>x,y</coordinates></Point>'
        b'</Placemark></kml>'
    )
    with pytest.raises(AnalysisError, match='Invalid marker coordinates'):
        read_markers(bad)
    with pytest.raises(AnalysisError, match='not a valid KML'):
        read_markers(b'<kml')


def test_poles_near_finds_the_poles_within_the_tolerance():
    poles = [pole(0, 1), pole(1, MATCH_TOLERANCE_M * 2), pole(2)]
    others = [pole(0), pole(1), pole(3)]

    assert poles_near(poles, others) == {0}


def test_poles_near_does_not_use_up_the_others():
    # Two markers on the same pole in use: both are in use
    used = [pole(0)]

    assert poles_near([pole(0, 2), pole(0, 1)], used) == {0, 1}


def test_poles_near_with_nothing_to_compare():
    assert poles_near([], [pole(0)]) == set()
    assert poles_near([pole(0)], []) == set()


def test_compare_city_classifies_each_pole():
    licensed = [
        (*pole(0, 1), 'matched'),
        (*pole(1, 1), 'matched too'),
        (*pole(1, 2), 'same pole in use'),
        (*pole(5), 'unused'),
    ]
    used = [pole(0), pole(1), pole(2), pole(3)]

    result = compare_city(licensed, used)

    assert [m[2] for m in result.matched] == [
        'matched',
        'matched too',
        'same pole in use',
    ]
    assert [m[2] for m in result.unused] == ['unused']
    assert result.unlicensed == [pole(2), pole(3)]
    assert len(result.matched) + len(result.unused) == len(licensed)
    assert result.used_poles == len(used)


# A cable 1 km long with no vertex but its two ends
CABLE = [[(LON, LAT), (LON + 0.01, LAT)]]


def test_cables_near_measures_the_distance_to_the_segment():
    on_the_middle = (LON + 0.005, LAT + 10 * ONE_M)
    too_far = (LON + 0.005, LAT + 30 * ONE_M)
    past_the_end = (LON + 0.01 + 40 * ONE_M, LAT)

    near = cables_near([on_the_middle, too_far, past_the_end], CABLE, 25.0)

    assert near == {0}


def test_cables_near_with_nothing_to_compare():
    assert cables_near([], CABLE, 25.0) == set()
    assert cables_near([pole(0)], [], 25.0) == set()


def test_cable_lines_survive_being_stored():
    cable = Cable('f', 'FO-12 x', 'FO-12', [[(-44.1234567, -20.7654321)]])

    assert decode_cable_lines(encode_cable_lines([cable])) == cable.lines


def test_a_marker_near_a_cable_is_in_use_without_a_pole():
    near_cable = (LON + 0.005, LAT + 10 * ONE_M, 'near the cable')
    far = (LON + 0.005, LAT + 100 * ONE_M, 'far')
    used = [pole(30)]

    with_cables = compare_city([near_cable, far], used, cables=[(CABLE, 25.0)])
    without = compare_city([near_cable, far], used)

    assert [m[2] for m in with_cables.matched] == ['near the cable']
    assert [m[2] for m in with_cables.unused] == ['far']
    # The analyses saved before the cables were kept still compare by pole
    assert without.matched == []


def test_compare_city_keeps_the_licensed_position():
    result = compare_city([(*pole(0, 1), 'x')], [pole(0)])

    assert result.matched == [(*pole(0, 1), 'x')]


def test_assign_markers_to_the_first_city_and_the_rest_outside(city_a, city_b):
    in_a = (-44.89, -20.14, 'a')
    in_b = (-44.87, -20.14, 'b')
    nowhere = (-46.0, -23.0, 'nowhere')

    inside, outside = assign_markers([in_b, in_a, nowhere], [city_a, city_b])

    assert inside == [[in_a], [in_b]]
    assert outside == [nowhere]


def test_run_licensed_groups_the_markers_by_city(routes_in_a_and_b):
    markers = [
        (-44.89, -20.14, 'a1'),
        (-44.895, -20.14, 'a2'),
        (-44.87, -20.14, 'b1'),
        (-46.0, -23.0, 'nowhere'),
    ]

    data = pipeline.run_licensed(sc.markers_kmz(markers), 'Licensed BH.kmz')

    assert data.code == f'{date.today().isoformat()}_Licensed BH'
    assert [(c.ibge_code, len(c.markers)) for c in data.cities] == [
        ('3122306', 2),
        ('3132404', 1),
    ]
    assert data.outside_markers == [(-46.0, -23.0, 'nowhere')]


def test_run_licensed_without_markers_is_an_analysis_error(
    routes_in_a_and_b,
):
    with pytest.raises(AnalysisError, match='No point markers'):
        pipeline.run_licensed(sc.markers_kmz([]), 'x.kmz')


def test_run_licensed_with_every_marker_outside_the_states(monkeypatch):
    def nowhere(*_):
        raise AnalysisError('The routes do not pass through any city.')

    monkeypatch.setattr(pipeline, 'find_cities', nowhere)

    with pytest.raises(AnalysisError, match='No licensed marker is inside'):
        pipeline.run_licensed(sc.markers_kmz([(0.0, 0.0, 'x')]), 'x.kmz')


def test_run_licensed_keeps_the_source_error(monkeypatch):
    def down(*_):
        raise SourceError('IBGE is down')

    monkeypatch.setattr(pipeline, 'find_cities', down)

    with pytest.raises(SourceError, match='IBGE is down'):
        pipeline.run_licensed(sc.markers_kmz([(-44.89, -20.14, 'x')]), 'x.kmz')


def test_comparison_kmz_has_a_folder_for_each_kind_of_pole():
    comparison = compare_city([(*pole(0, 1), 'x')], [pole(0), pole(1)])

    kmz = comparison_kmz('t', [comparison], [(*pole(7), 'p')], [])

    assert kmz[:2] == b'PK'
    kml = read_kml(kmz)
    for folder in (
        'Licenciado e utilizado (1)',
        'Utilizado sem licença (1)',
        'Licenciado sem uso (0)',
        'Licenciado, aguardando cabos da cidade (1)',
        'Licenciado fora das cidades de MG e SP (0)',
    ):
        assert folder in kml


def read_kml(kmz: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(kmz)) as archive:
        return archive.read('doc.kml').decode()


async def test_a_new_licensing_replaces_the_cities_it_covers(
    session, routes_in_a_and_b
):
    in_a, in_b = (-44.89, -20.14, 'a'), (-44.87, -20.14, 'b')
    both = pipeline.run_licensed(sc.markers_kmz([in_a, in_b]), 'both.kmz')
    await licensed_service.save_licensed(session, both)
    new_a = pipeline.run_licensed(sc.markers_kmz([in_a]), 'new_a.kmz')
    await licensed_service.save_licensed(session, new_a)

    sets = await licensed_service.list_licensed(session, 10, 0)

    assert {
        s.code.split('_', 1)[1]: [c.ibge_code for c in s.cities] for s in sets
    } == {'both': ['3132404'], 'new_a': ['3122306']}


async def test_a_licensing_left_without_cities_is_removed(
    session, routes_in_a_and_b
):
    in_a = (-44.89, -20.14, 'a')
    for name in ('old.kmz', 'new.kmz'):
        data = pipeline.run_licensed(sc.markers_kmz([in_a]), name)
        await licensed_service.save_licensed(session, data)

    sets = await licensed_service.list_licensed(session, 10, 0)

    assert [s.code.split('_', 1)[1] for s in sets] == ['new']


async def test_a_city_is_compared_with_its_latest_backbone_and_analysis(
    session, backbone_data, analysis_data
):
    older = backbone_data.model_copy(
        update={'code': 'old_backbone', 'backbone_date': date(2020, 1, 1)}
    )
    await backbone_service.save_backbone(session, older)
    only_old = await licensed_service.latest_sources(session, ['3122306'])
    assert [s.code for s in only_old['3122306']] == ['old_backbone']

    await analysis_service.save_analysis(session, analysis_data)
    both = await licensed_service.latest_sources(
        session, ['3122306', '3132404', '9999999']
    )

    # The latest first, and one per kind: a backbone and an analysis of the
    # same city are both poles in use
    assert [(s.kind, s.code) for s in both['3122306']] == [
        ('analysis', analysis_data.code),
        ('backbone', 'old_backbone'),
    ]
    assert [s.code for s in both['3132404']] == ['old_backbone']
    assert '9999999' not in both


async def test_every_backbone_and_only_the_latest_analysis_are_compared(
    session, backbone_data, analysis_data
):
    for name, day in (('old', date(2020, 1, 1)), ('new', date(2021, 1, 1))):
        data = backbone_data.model_copy(
            update={'code': name, 'backbone_date': day}
        )
        await backbone_service.save_backbone(session, data)
    for name, day in (('a1', date(2019, 1, 1)), ('a2', date(2022, 1, 1))):
        data = analysis_data.model_copy(
            update={'code': name, 'analysis_date': day}
        )
        await analysis_service.save_analysis(session, data)

    sources = await licensed_service.latest_sources(session, ['3122306'])

    assert [(s.kind, s.code) for s in sources['3122306']] == [
        ('analysis', 'a2'),
        ('backbone', 'new'),
        ('backbone', 'old'),
    ]


def test_merge_used_joins_the_poles_of_the_sources_once():
    def source(row_id):
        return licensed_service.UsedSource(
            'analysis', 'x', date.today(), datetime.now(), row_id, 25.0
        )

    first, second = uuid4(), uuid4()
    files = {
        first: licensed_service.UsedFiles(
            all_poles_kmz('a', [pole(0), pole(1)]), None
        ),
        # pole(1) is in both, and pole(2) only in the second
        second: licensed_service.UsedFiles(
            all_poles_kmz('b', [pole(1), pole(2)]),
            encode_cable_lines([Cable('f', 'FO-12', 'FO-12', CABLE)]),
        ),
    }

    used, cables = licensed_service.merge_used(
        [source(first), source(second)], files
    )

    assert sorted(used) == sorted([pole(0), pole(1), pole(2)])
    assert cables == [(CABLE, 25.0)]


async def test_the_cables_are_stored_and_used_to_compare(
    session, backbone_data
):
    await backbone_service.save_backbone(session, backbone_data)
    sources = await licensed_service.latest_sources(session, ['3122306'])
    files = await licensed_service.used_files(session, sources)

    (source,) = sources['3122306']
    assert source.radius_m == backbone_data.radius_m
    assert decode_cable_lines(files[source.row_id].cable_lines)
    # A marker on the main cable, away from every pole in use
    on_the_cable = [(-44.8851, sc.LAT - 0.00002, 'on the cable')]
    result = licensed_service.compare_sources(
        SimpleNamespace(
            cities=[
                SimpleNamespace(
                    ibge_code='3122306', markers=on_the_cable, poles=1
                )
            ],
            outside_markers=[],
        ),
        sources,
        files,
    )
    assert len(result.cities[0].comparison.matched) == 1
