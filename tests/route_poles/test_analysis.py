"""The analysis layer against the golden files, which hold the outputs of the
code before the v8 refactor.
"""

import io
import json
import struct
import tarfile

import pytest

from app.modules.route_poles.analysis import city as city_module
from app.modules.route_poles.analysis import city_poles as city_poles_module
from app.modules.route_poles.analysis import pipeline
from app.modules.route_poles.analysis.city import (
    find_cities,
    find_city,
)
from app.modules.route_poles.analysis.clip import clip_lines
from app.modules.route_poles.analysis.engine import analyze
from app.modules.route_poles.analysis.errors import AnalysisError, SourceError
from app.modules.route_poles.analysis.pole_base import (
    lat_to_tile_y,
    lon_to_tile_x,
    read_poles,
)
from app.modules.route_poles.analysis.routes import read_cables
from app.modules.route_poles.constants import DEFAULT_RADIUS_M
from app.modules.route_poles.schemas import AnalysisOptions, RouteUploadOptions
from tests.route_poles import scenarios as sc
from tests.route_poles.conftest import make_city
from tests.route_poles.golden_support import (
    describe_city,
    describe_data,
    describe_engine,
    describe_lines,
    load_golden,
)

VERTICES = sc.route_vertices()
MULTI_LINES = 2
OUTSIDE = [(-40.0, -12.0), (-40.01, -12.01)]
# name: (function, arguments, FakeIbge options)
LOOKUPS = {
    'by_code': (find_city, (VERTICES, None, '3122306'), {}),
    'by_name': (find_city, (VERTICES, 'divinopolis', None), {}),
    'by_routes': (find_city, (VERTICES,), {}),
    'by_code_mesh_down': (
        find_city,
        (VERTICES, None, '3122306'),
        {'fail': ['/malhas/municipios/']},
    ),
    'by_routes_first_source_down': (
        find_city,
        (VERTICES,),
        {'fail': ['/malhas/estados/']},
    ),
    'by_code_all_down': (
        find_city,
        (VERTICES, None, '3122306'),
        {'fail': ['/malhas/', 'geojs-']},
    ),
    'by_code_missing_in_first_source': (
        find_city,
        (VERTICES, None, '3122306'),
        {
            'fail': ['/malhas/municipios/'],
            'omit_in_ibge_state_mesh': ['3122306'],
        },
    ),
    'by_code_missing_everywhere': (
        find_city,
        (VERTICES, None, '3122306'),
        {
            'fail': ['/malhas/municipios/', 'geojs-'],
            'omit_in_ibge_state_mesh': ['3122306'],
        },
    ),
    'name_unknown': (find_city, (VERTICES, 'Atlantis', None), {}),
    'name_ambiguous': (
        find_city,
        (VERTICES, 'Divinopolis', None),
        {'homonym': True},
    ),
    'name_list_down': (
        find_city,
        (VERTICES, 'Divinopolis', None),
        {'fail': ['/localidades/estados/']},
    ),
    'cities_by_routes': (find_cities, (VERTICES,), {}),
    'cities_mesh_down': (
        find_cities,
        (VERTICES,),
        {'fail': ['/malhas/municipios/']},
    ),
    'cities_first_source_down': (
        find_cities,
        (VERTICES,),
        {'fail': ['/malhas/estados/']},
    ),
    'cities_all_down': (
        find_cities,
        (VERTICES,),
        {'fail': ['/malhas/estados/', 'geojs-']},
    ),
    'cities_outside': (find_cities, (OUTSIDE,), {}),
}


def run_lookup(monkeypatch, name):
    function, args, ibge_options = LOOKUPS[name]
    ibge = sc.FakeIbge(**ibge_options)
    monkeypatch.setattr(city_module, 'fetch', ibge)
    try:
        found = function(*args)
        result = (
            [describe_city(c) for c in found]
            if isinstance(found, list)
            else describe_city(found)
        )
    except AnalysisError as error:
        result = {'error': type(error).__name__}
    calls = [url.split('?')[0].replace('https://', '') for url in ibge.calls]
    return {'result': result, 'calls': calls}


@pytest.mark.parametrize('name', LOOKUPS)
def test_city_lookup_matches_golden(monkeypatch, name):
    assert run_lookup(monkeypatch, name) == load_golden('lookup')[name]


def test_city_lookup_error_messages_are_in_english(monkeypatch):
    monkeypatch.setattr(city_module, 'fetch', sc.FakeIbge())
    with pytest.raises(AnalysisError, match="City 'Atlantis' not found"):
        find_city(VERTICES, 'Atlantis')

    monkeypatch.setattr(city_module, 'fetch', sc.FakeIbge(homonym=True))
    with pytest.raises(AnalysisError, match='more than one city'):
        find_city(VERTICES, 'Divinopolis')

    monkeypatch.setattr(
        city_module, 'fetch', sc.FakeIbge(fail=['/malhas/', 'geojs-'])
    )
    with pytest.raises(SourceError, match='Could not get the city boundary'):
        find_city(VERTICES, None, '3122306')


def test_routes_outside_every_city_are_not_given_a_city(monkeypatch):
    monkeypatch.setattr(city_module, 'fetch', sc.FakeIbge())
    with pytest.raises(AnalysisError, match='not inside any city'):
        find_city(OUTSIDE)


def test_clip_lines_matches_golden(city_a):
    cases = {
        'crossing': [sc.MAIN_CABLE],
        'inside': [[(-44.899, -20.139), (-44.890, -20.141)]],
        'outside': [[(-44.870, -20.139), (-44.865, -20.141)]],
        'reenter': [
            [
                (-44.890, -20.140),
                (-44.870, -20.140),
                (-44.870, -20.135),
                (-44.890, -20.135),
            ]
        ],
        'vertex_on_border': [[(-44.890, -20.140), (-44.880, -20.140)]],
        'two_lines': [
            [(-44.895, -20.139), (-44.885, -20.139)],
            [(-44.885, -20.141), (-44.875, -20.141)],
        ],
    }
    golden = load_golden('clip')
    for name, lines in cases.items():
        clipped = describe_lines(clip_lines(lines, city_a.area))
        assert clipped == golden[name], name


def test_engine_matches_golden():
    cables = read_cables(sc.routes_kml())
    poles = sc.CEMIG_POLES + sc.DME_POLES
    result = analyze(cables, poles, 25.0, with_stretches=True)
    described = json.loads(json.dumps(describe_engine(cables, result)))
    assert described == load_golden('engine')


def test_read_cables_skips_excluded_cables_and_types_the_rest():
    cables = read_cables(sc.routes_kmz())
    assert [c.name for c in cables] == [
        'FO-12 Backbone',
        'FO-06 Duplicate',
        'FO-144 Parallel',
        'Loose cable',
        'FO-48 Multi',
        'F0-24 Letter zero',
    ]
    assert [c.cable_type for c in cables] == [
        'FO-12',
        'FO-06',
        'FO-144',
        'não informado',
        'FO-48',
        'FO-24',
    ]
    assert [c.folder for c in cables][:2] == ['Backbone', 'Ramais']
    assert len(cables[4].lines) == MULTI_LINES


@pytest.mark.parametrize(
    ('name', 'filename', 'options'),
    [
        ('single_plain', 'backbone_bh.kmz', {}),
        (
            'single_full',
            'backbone_bh.kmz',
            {
                'export_all': True,
                'overlap_kmz': True,
                'overlap_split_kmz': True,
            },
        ),
        (
            'single_wide',
            'plain.kml',
            {'radius_m': 40.0, 'overlap_split_kmz': True},
        ),
    ],
)
def test_run_analysis_matches_golden(
    routes_in_a_and_b, name, filename, options
):
    content = sc.routes_kml() if filename.endswith('.kml') else sc.routes_kmz()
    data = pipeline.run_analysis(
        content, filename, RouteUploadOptions(**options)
    )
    assert describe_data(data) == load_golden('pipeline')[name]


CITY_ONLY_FIELDS = {'code', 'analysis_date', 'routes_file', 'radius_m'}


@pytest.mark.parametrize(
    ('name', 'options'),
    [
        ('split_plain', {}),
        (
            'split_full',
            {
                'export_all': True,
                'overlap_kmz': True,
                'overlap_split_kmz': True,
            },
        ),
    ],
)
def test_run_backbone_matches_golden(routes_in_a_and_b, name, options):
    backbone = pipeline.run_backbone(
        sc.routes_kmz(), 'backbone_bh.kmz', AnalysisOptions(**options)
    )
    expected = load_golden('pipeline')[name]
    assert [describe_data(c) for c in backbone.cities] == [
        {k: v for k, v in city.items() if k not in CITY_ONLY_FIELDS}
        for city in expected
    ]
    assert backbone.routes_file == 'backbone_bh.kmz'
    assert backbone.radius_m == DEFAULT_RADIUS_M
    assert backbone.code.endswith('_backbone_bh')
    assert backbone.backbone_date.isoformat() in backbone.code


def test_backbone_cities_add_up_to_the_whole_route(routes_in_a_and_b):
    backbone = pipeline.run_backbone(
        sc.routes_kmz(), 'backbone_bh.kmz', AnalysisOptions()
    )
    whole = pipeline.run_analysis(
        sc.routes_kmz(), 'backbone_bh.kmz', RouteUploadOptions()
    )
    by_city = sum(city.route_length_m for city in backbone.cities)
    # The cut at the border moves the length by a few meters
    assert by_city == pytest.approx(whole.route_length_m, abs=15)
    assert [c.ibge_code for c in backbone.cities] == ['3122306', '3132404']


def test_no_poles_in_the_cities_is_an_analysis_error(
    monkeypatch, routes_in_a_and_b
):
    monkeypatch.setattr(city_poles_module, 'read_poles', sc.empty_read_poles)
    with pytest.raises(AnalysisError, match='No poles from the pole bases'):
        pipeline.run_analysis(sc.routes_kmz(), 'x.kmz', RouteUploadOptions())
    with pytest.raises(AnalysisError, match='No poles from the pole bases'):
        pipeline.run_backbone(sc.routes_kmz(), 'x.kmz', AnalysisOptions())


def test_file_without_lines_is_an_analysis_error(routes_in_a_and_b):
    empty = sc.routes_kml({})
    with pytest.raises(AnalysisError, match='No lines found'):
        pipeline.run_analysis(empty, 'x.kml', RouteUploadOptions())


def test_invalid_files_are_analysis_errors(routes_in_a_and_b):
    with pytest.raises(AnalysisError, match='not a valid KML'):
        pipeline.run_analysis(b'<kml', 'x.kml', RouteUploadOptions())
    with pytest.raises(AnalysisError, match='Corrupted KMZ'):
        pipeline.run_analysis(b'PK\x03\x04junk', 'x.kmz', RouteUploadOptions())


def test_poles_in_cities_gives_a_shared_pole_to_the_first_city(
    pole_bases, city_a
):
    overlapping_b = make_city(sc.CITY_B, sc.CITY_B_OVERLAP_BOX)
    shared = (-44.8804, -20.13997)
    assert city_a.area.contains(*shared)
    assert overlapping_b.area.contains(*shared)

    in_a, in_b = city_poles_module.poles_in_cities([city_a, overlapping_b])
    assert shared in in_a.poles
    assert shared not in in_b.poles


def test_base_label_lists_only_bases_with_a_meaningful_share(
    pole_bases, city_a, city_b
):
    in_a, in_b = city_poles_module.poles_in_cities([city_a, city_b])
    assert in_a.base_label == 'BDGD Cemig-D 2025-12-31'
    assert in_b.base_label == 'BDGD Cemig-D 2025-12-31 + BDGD DME'


def tile_base(path, tiles: dict[tuple[int, int], int]):
    """A pole base .tar.gz with n poles in each (tx, ty) tile."""
    with tarfile.open(path, 'w:gz') as tar:
        files = {'v1/manifest.json': b'{"data_base": "2025-12-31"}'}
        for (tx, ty), n in tiles.items():
            files[f'v1/{tx}/{ty}.bin'] = struct.pack('<HH', 100, 200) * n
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return path


def test_read_poles_decodes_only_the_tiles_crossing_the_boxes(tmp_path):
    lon, lat = -44.88, -20.14
    tx, ty = int(lon_to_tile_x(lon)), int(lat_to_tile_y(lat))
    base = tile_base(
        tmp_path / 'base.tar.gz',
        {(tx, ty): 3, (tx + 5, ty): 7, (tx, ty + 5): 11},
    )
    tiles = []

    manifest = read_poles(
        base, [(lon, lat, lon, lat)], lambda poles: tiles.append(len(poles))
    )

    assert tiles == [3]
    assert manifest == {'data_base': '2025-12-31'}


def test_read_poles_reads_the_tiles_of_every_box(tmp_path):
    first, second = (-44.88, -20.14), (-45.5, -19.5)
    tiles_of = [
        (int(lon_to_tile_x(lon)), int(lat_to_tile_y(lat)))
        for lon, lat in (first, second)
    ]
    base = tile_base(
        tmp_path / 'base.tar.gz', {tiles_of[0]: 2, tiles_of[1]: 4}
    )
    tiles = []

    read_poles(
        base,
        [(*first, *first), (*second, *second)],
        lambda poles: tiles.append(len(poles)),
    )

    assert sorted(tiles) == [2, 4]
