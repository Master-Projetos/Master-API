"""City boundary (IBGE), found by IBGE code, by name or by the routes."""

import json
import logging
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass

from ..constants import STATES
from .errors import AnalysisError, SourceError
from .geometry import LonLat
from .http import fetch

logger = logging.getLogger(__name__)

IBGE_CITIES_URL = (
    'https://servicodados.ibge.gov.br/api/v1/localidades/estados/{state}'
    '/municipios'
)
IBGE_CITY_MESH_URL = (
    'https://servicodados.ibge.gov.br/api/v3/malhas/municipios/{code}'
    '?formato=application/vnd.geo%2Bjson&qualidade=maxima'
)
IBGE_STATE_MESH_URL = (
    'https://servicodados.ibge.gov.br/api/v3/malhas/estados/{state}'
    '?formato=application/vnd.geo%2Bjson&intrarregiao=municipio'
    '&qualidade=intermediaria'
)
GEODATA_BR_URL = (
    'https://raw.githubusercontent.com/tbrugz/geodata-br/master/geojson'
    '/geojs-{state}-mun.json'
)
CITY_MESH_LABEL = 'IBGE city mesh (maximum quality)'
# In order of preference
STATE_MESH_SOURCES = (
    (IBGE_STATE_MESH_URL, 'IBGE state mesh (intermediate quality)'),
    (GEODATA_BR_URL, 'geodata-br (simplified IBGE)'),
)

# Route vertices sampled to find the city the routes are in
DETECTION_SAMPLE = 400
# Route vertices sampled to find every city the routes pass through
ALL_CITIES_SAMPLE = 5000
IBGE_CODE_HINT = 'Provide the IBGE code (ibge_code).'


class Area:
    """(Multi)polygon in lon/lat, with a point-in-polygon test."""

    def __init__(self, polygons: list):
        self.polygons = polygons
        xs = [c[0] for p in polygons for c in p[0]]
        ys = [c[1] for p in polygons for c in p[0]]
        self.bbox = (min(xs), min(ys), max(xs), max(ys))
        self.boxes = []
        for p in polygons:
            px = [c[0] for c in p[0]]
            py = [c[1] for c in p[0]]
            self.boxes.append((min(px), min(py), max(px), max(py)))

    def contains(self, x: float, y: float) -> bool:
        for polygon, (x0, y0, x1, y1) in zip(self.polygons, self.boxes):
            if (
                x0 <= x <= x1
                and y0 <= y <= y1
                and _in_ring(x, y, polygon[0])
                and not any(_in_ring(x, y, hole) for hole in polygon[1:])
            ):
                return True
        return False


@dataclass
class City:
    code: str
    name: str
    area: Area


def _in_ring(x: float, y: float, ring) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _polygons(geometry: dict) -> list:
    match geometry['type']:
        case 'Polygon':
            return [geometry['coordinates']]
        case 'MultiPolygon':
            return geometry['coordinates']
        case 'GeometryCollection':
            return [p for g in geometry['geometries'] for p in _polygons(g)]
    return []


def _feature_code(props: dict) -> str:
    for key in (
        'codarea',
        'id',
        'CD_MUN',
        'cd_mun',
        'geocodigo',
        'GEOCODIGO',
        'codigo',
    ):
        if props.get(key) is not None:
            return str(props[key])
    return ''


def _feature_name(props: dict) -> str:
    for key in ('name', 'nome', 'NM_MUN', 'nm_mun', 'description'):
        if props.get(key):
            return str(props[key])
    return ''


def _plain(text: str) -> str:
    """Accent and case insensitive key: 'Taubaté' == 'TAUBATE'."""
    decomposed = unicodedata.normalize('NFD', text)
    return (
        ''
        .join(c for c in decomposed if unicodedata.category(c) != 'Mn')
        .lower()
        .strip()
    )


def _states_label(states) -> str:
    return '/'.join(STATES.get(s, f'UF {s}') for s in states)


def _describe(error: Exception) -> str:
    return f'{type(error).__name__}: {error}'


def _city_names(state: str) -> dict[str, str]:
    """IBGE code -> name of the cities of a state; {} when IBGE fails."""
    try:
        cities = json.loads(fetch(IBGE_CITIES_URL.format(state=state)))
    except Exception:
        logger.warning('IBGE city list of state %s unavailable', state)
        return {}
    return {str(c['id']): c['nome'] for c in cities}


def _code_by_name(name: str, names: dict[str, str], incomplete: bool) -> str:
    wanted = _plain(name)
    found = [code for code, n in names.items() if _plain(n) == wanted]
    if not found and incomplete:
        raise SourceError(
            f"The IBGE city list did not answer, so '{name}' can't be found "
            'by name. Try again or provide the IBGE code (ibge_code).'
        )
    if not found:
        raise AnalysisError(
            f"City '{name}' not found in {_states_label(STATES)}. "
            + IBGE_CODE_HINT
        )
    if len(found) > 1:
        options = ', '.join(f'{_states_label([c[:2]])}: {c}' for c in found)
        raise AnalysisError(
            f"There is more than one city '{name}' ({options}). "
            + IBGE_CODE_HINT
        )
    return found[0]


def _city_mesh(code: str) -> Area:
    geojson = json.loads(fetch(IBGE_CITY_MESH_URL.format(code=code)))
    feature = (
        geojson['features'][0]
        if geojson.get('type') == 'FeatureCollection'
        else geojson
    )
    return Area(_polygons(feature.get('geometry', feature)))


def _best_mesh_city(code: str, name: str, failures: list[str]) -> City | None:
    """The city with its best quality boundary; None when IBGE fails."""
    try:
        return City(code, name, _city_mesh(code))
    except Exception as error:
        failures.append(f'{CITY_MESH_LABEL}: {_describe(error)}')
        logger.warning('IBGE city mesh of %s unavailable: %s', code, error)
        return None


def _state_meshes(
    state: str, failures: list[str]
) -> Iterator[tuple[list, str]]:
    """(city features, label) of each source that answers for the state."""
    for url, source in STATE_MESH_SOURCES:
        label = f'{source} {_states_label([state])}'
        try:
            features = json.loads(fetch(url.format(state=state)))['features']
        except Exception as error:
            failures.append(f'{label}: {_describe(error)}')
            logger.warning('%s unavailable: %s', label, error)
            continue
        yield features, label


def _most_points(
    features: list, points: list[LonLat]
) -> tuple[dict, int, int]:
    """(feature with most sampled route vertices, vertices in it, sample)."""
    sample = points[:: max(1, len(points) // DETECTION_SAMPLE)]
    best, best_count = None, -1
    for feature in features:
        area = Area(_polygons(feature['geometry']))
        count = sum(1 for x, y in sample if area.contains(x, y))
        if count > best_count:
            best, best_count = feature, count
    return best, best_count, len(sample)


def _feature_by_code(code: str, failures: list[str]) -> dict | None:
    for features, label in _state_meshes(code[:2], failures):
        for feature in features:
            if _feature_code(feature.get('properties') or {}) == code:
                return feature
        failures.append(f'{label}: city {code} is not in the mesh')
    return None


def _feature_by_routes(
    states: list[str], points: list[LonLat], failures: list[str]
) -> dict:
    """The city with most route vertices. The next state is tried only when
    most of the route is outside the best city of the current one.
    """
    best: tuple[int, dict] | None = None
    for state in states:
        sample = 0
        for features, _ in _state_meshes(state, failures):
            feature, inside, sample = _most_points(features, points)
            if best is None or inside > best[0]:
                best = (inside, feature)
            break
        if best and 2 * best[0] > sample:
            break
    if best is None:
        raise _boundary_error(failures)
    if best[0] == 0:
        raise AnalysisError(
            f'The routes are not inside any city of {_states_label(STATES)}. '
            + IBGE_CODE_HINT
        )
    return best[1]


def _boundary_error(failures: list[str]) -> SourceError:
    return SourceError(
        'Could not get the city boundary from any source ('
        + '; '.join(failures)
        + ').'
    )


def find_city(
    points: list[LonLat], name: str | None = None, code: str | None = None
) -> City:
    """The city by IBGE code, else by name (MG and SP), else the one with
    most of the route vertices (MG first, then SP).

    Raises AnalysisError (city not found) or SourceError (IBGE down).
    """
    # A city code starts with its state code
    states = [code[:2]] if code else list(STATES)
    names: dict[str, str] = {}
    incomplete = False
    for state in states:
        state_names = _city_names(state)
        names.update(state_names)
        incomplete = incomplete or not state_names
    if not code and name:
        code = _code_by_name(name, names, incomplete)
        states = [code[:2]]
    elif code and (code[:2] not in STATES or (names and code not in names)):
        raise AnalysisError(
            f'IBGE code {code} is not a city of {_states_label(STATES)}.'
        )

    failures: list[str] = []
    if code:
        city = _best_mesh_city(code, names.get(code, name or code), failures)
        if city:
            return city
        feature = _feature_by_code(code, failures)
        if feature is None:
            raise _boundary_error(failures)
    else:
        feature = _feature_by_routes(states, points, failures)

    props = feature.get('properties') or {}
    found_code = _feature_code(props)
    found_name = names.get(found_code) or _feature_name(props) or found_code
    if not code:
        logger.info(
            'city detected by the routes: %s (%s)', found_name, found_code
        )
        city = _best_mesh_city(found_code, found_name, failures)
        if city:
            return city
    return City(found_code, found_name, Area(_polygons(feature['geometry'])))


def _boxes_overlap(a: tuple, b: tuple) -> bool:
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def find_cities(
    points: list[LonLat], sample_size: int = ALL_CITIES_SAMPLE
) -> list[City]:
    """Every city (MG and SP) the points are in, most points first.

    Only about sample_size points are looked at: pass len(points) when a city
    with a few points can't be missed.

    Raises AnalysisError (route outside MG/SP) or SourceError (IBGE down).
    """
    sample = points[:: max(1, len(points) // sample_size)]
    route_box = (
        min(p[0] for p in sample),
        min(p[1] for p in sample),
        max(p[0] for p in sample),
        max(p[1] for p in sample),
    )
    names: dict[str, str] = {}
    failures: list[str] = []
    # (vertices inside, code, state mesh area)
    found: list[tuple[int, str, Area]] = []
    remaining = sample
    for state in STATES:
        names.update(_city_names(state))
        mesh = next(_state_meshes(state, failures), None)
        if mesh is None:
            # A missing state could hide some of the cities
            raise SourceError(
                'Could not get the city boundaries of '
                f'{_states_label([state])} (' + '; '.join(failures) + ').'
            )
        for feature in mesh[0]:
            area = Area(_polygons(feature['geometry']))
            if not _boxes_overlap(area.bbox, route_box):
                continue
            x0, y0, x1, y1 = area.bbox
            outside = [
                p
                for p in remaining
                if not (x0 <= p[0] <= x1 and y0 <= p[1] <= y1)
                or not area.contains(*p)
            ]
            if len(outside) < len(remaining):
                code = _feature_code(feature.get('properties') or {})
                found.append((len(remaining) - len(outside), code, area))
                remaining = outside
    if not found:
        raise AnalysisError(
            'The routes do not pass through any city of '
            f'{_states_label(STATES)}.'
        )

    cities = []
    for _, code, area in sorted(found, key=lambda f: -f[0]):
        name = names.get(code) or code
        cities.append(
            _best_mesh_city(code, name, failures) or City(code, name, area)
        )
    logger.info(
        'cities detected by the routes: %s',
        ', '.join(f'{c.name} ({c.code})' for c in cities),
    )
    return cities
