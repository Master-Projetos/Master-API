"""Synthetic inputs shared by the route poles tests.

Two adjacent rectangular cities (A and B) near Divinopolis, a routes file that
crosses both, and two fake pole bases.
"""

import io
import json
import re
import zipfile
from pathlib import Path

from app.modules.route_poles.analysis.pole_base import POLE_BASES

LonLat = tuple[float, float]

CITY_A = ('3122306', 'Divinópolis')
CITY_B = ('3132404', 'Itaúna')
CITY_SP = ('3550308', 'São Paulo')
CITY_A_BOX = (-44.900, -20.150, -44.880, -20.130)
CITY_B_BOX = (-44.880, -20.150, -44.860, -20.130)
CITY_B_OVERLAP_BOX = (-44.8806, -20.150, -44.860, -20.130)
CITY_SP_BOX = (-46.800, -23.800, -46.400, -23.400)
LAT = -20.140


def ring(box: tuple[float, float, float, float]) -> list[LonLat]:
    x0, y0, x1, y1 = box
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]


def line_points(
    lon0: float, step: float, count: int, lat: float
) -> list[LonLat]:
    return [(round(lon0 + i * step, 7), lat) for i in range(count)]


MAIN_CABLE = [(-44.895, LAT), (-44.870, LAT), (-44.865, -20.1405)]
CABLES = {
    'Backbone': [
        ('FO-12 Backbone', [MAIN_CABLE]),
        ('DROP-77 Client', [[(-44.890, -20.1380), (-44.889, -20.1380)]]),
    ],
    'Ramais': [
        ('FO-06 Duplicate', [[(-44.8930, LAT), (-44.8860, LAT)]]),
        (
            'FO-144 Parallel',
            [[(-44.8920, -20.13993), (-44.8870, -20.13993)]],
        ),
        ('Loose cable', [[(-44.8700, -20.1360), (-44.8650, -20.1380)]]),
        ('MIT-3 Internal', [[(-44.8800, -20.1350), (-44.8790, -20.1350)]]),
    ],
    'Multi': [
        (
            'FO-48 Multi',
            [
                [(-44.899, -20.1450), (-44.896, -20.1450)],
                [(-44.899, -20.1435), (-44.896, -20.1435)],
            ],
        ),
        ('F0-24 Letter zero', [[(-44.872, -20.1330), (-44.862, -20.1330)]]),
    ],
}
MARKER = (
    '<Placemark><name>Marker</name><Point><coordinates>-44.89,-20.14,0'
    '</coordinates></Point></Placemark>'
)


def placemark_xml(name: str, lines: list[list[LonLat]]) -> str:
    geometries = ''.join(
        '<LineString><coordinates>'
        + ' '.join(f'{lon},{lat},0' for lon, lat in line)
        + '</coordinates></LineString>'
        for line in lines
    )
    if len(lines) > 1:
        geometries = f'<MultiGeometry>{geometries}</MultiGeometry>'
    return f'<Placemark><name>{name}</name>{geometries}</Placemark>'


def routes_kml(cables=CABLES) -> bytes:
    folders = ''.join(
        f'<Folder><name>{folder}</name>'
        + ''.join(placemark_xml(name, lines) for name, lines in items)
        + (MARKER if folder == 'Backbone' else '')
        + '</Folder>'
        for folder, items in cables.items()
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        f'<name>Routes</name>{folders}</Document></kml>'
    ).encode()


def routes_kmz(cables=CABLES) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as kmz:
        kmz.writestr('doc.kml', routes_kml(cables))
    return buffer.getvalue()


CEMIG_POLES = [
    *line_points(-44.896, 0.0004, 81, -20.13997),
    *line_points(-44.899, 0.004, 10, -20.1450),
    (-44.8695, -20.1365),
    (-44.8670, -20.1375),
    (-44.8700, -20.13297),
    (-44.8660, -20.13297),
    (-44.8625, -20.13297),
    (-44.8975, -20.14497),
    (-44.8975, -20.14347),
]
DME_POLES = [
    (-44.8990, -20.1320),
    (-44.8650, -20.1450),
    (-44.8640, -20.1450),
    (-44.8630, -20.1450),
]
BASE_POLES = {'cemig': CEMIG_POLES, 'dme': DME_POLES}
BASE_MANIFESTS = {'cemig': {'data_base': '2025-12-31'}, 'dme': {}}


def fake_local_bases():
    return [(POLE_BASES[0], Path('cemig')), (POLE_BASES[1], Path('dme'))]


def fake_read_poles(path, bbox):
    min_lon, min_lat, max_lon, max_lat = bbox
    poles = [
        p
        for p in BASE_POLES[path.name]
        if min_lon <= p[0] <= max_lon and min_lat <= p[1] <= max_lat
    ]
    return poles, BASE_MANIFESTS[path.name]


def empty_read_poles(path, bbox):
    return [], {}


def route_vertices() -> list[LonLat]:
    return [
        point
        for items in CABLES.values()
        for _, lines in items
        for line in lines
        for point in line
    ]


def geojson_polygon(box) -> dict:
    return {'type': 'Polygon', 'coordinates': [ring(box)]}


def geojson_multipolygon(box) -> dict:
    return {'type': 'MultiPolygon', 'coordinates': [[ring(box)]]}


STATE_CITIES = {
    '31': [
        (*CITY_A, CITY_A_BOX, geojson_polygon),
        (*CITY_B, CITY_B_BOX, geojson_multipolygon),
    ],
    '35': [(*CITY_SP, CITY_SP_BOX, geojson_polygon)],
}


class FakeIbge:
    """Stands in for city.fetch.

    fail: URL fragments that raise OSError.
    omit_in_ibge_state_mesh: city codes missing from the IBGE state mesh only.
    homonym: adds a city named like city A to the São Paulo list.
    """

    def __init__(self, fail=(), omit_in_ibge_state_mesh=(), homonym=False):
        self.fail = tuple(fail)
        self.omit = set(omit_in_ibge_state_mesh)
        self.homonym = homonym
        self.calls: list[str] = []

    def __call__(self, url: str, timeout: float = 120) -> bytes:
        self.calls.append(url)
        if any(fragment in url for fragment in self.fail):
            raise OSError(f'unreachable: {url}')
        return json.dumps(self.answer(url)).encode()

    def answer(self, url: str):
        match = re.search(r'estados/(\d+)|geojs-(\d+)-mun', url)
        state = (match.group(1) or match.group(2)) if match else None
        if '/localidades/estados/' in url:
            cities = [
                {'id': int(code), 'nome': name}
                for code, name, _, _ in STATE_CITIES[state]
            ]
            if self.homonym and state == '35':
                cities.append({'id': 3599999, 'nome': CITY_A[1]})
            return cities
        if '/malhas/municipios/' in url:
            code = url.split('/malhas/municipios/')[1].split('?', 1)[0]
            for cities in STATE_CITIES.values():
                for city_code, _, box, geometry in cities:
                    if city_code == code:
                        return {
                            'type': 'FeatureCollection',
                            'features': [
                                {
                                    'type': 'Feature',
                                    'properties': {},
                                    'geometry': geometry(box),
                                }
                            ],
                        }
            raise OSError(f'no mesh: {url}')
        if '/malhas/estados/' in url:
            return {
                'type': 'FeatureCollection',
                'features': [
                    {
                        'type': 'Feature',
                        'properties': {'codarea': code},
                        'geometry': geometry(box),
                    }
                    for code, _, box, geometry in STATE_CITIES[state]
                    if code not in self.omit
                ],
            }
        if 'geojs-' in url:
            return {
                'type': 'FeatureCollection',
                'features': [
                    {
                        'type': 'Feature',
                        'properties': {'id': code, 'name': name},
                        'geometry': geometry(box),
                    }
                    for code, name, box, geometry in STATE_CITIES[state]
                ],
            }
        raise OSError(f'unexpected url: {url}')
