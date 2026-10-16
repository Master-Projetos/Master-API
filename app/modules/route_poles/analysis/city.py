"""City boundary (IBGE), found by IBGE code, by name or by the routes."""

import json
import logging
import unicodedata
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
CITY_MESH_SOURCE = 'IBGE malha municipal (qualidade máxima)'
STATE_MESH_SOURCES = (
    (IBGE_STATE_MESH_URL, 'IBGE malha estadual (qualidade intermediária)'),
    (GEODATA_BR_URL, 'geodata-br (IBGE simplificado)'),
)

# Route vertices sampled to find the city the routes are in
DETECTION_SAMPLE = 400
IBGE_CODE_HINT = 'Informe o código IBGE (ibge_code).'


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
    boundary_source: str


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


def _city_names(state: str) -> dict[str, str]:
    """IBGE code -> name of the cities of a state; {} when IBGE fails."""
    try:
        cities = json.loads(fetch(IBGE_CITIES_URL.format(state=state)))
    except Exception:
        logger.warning('IBGE city list of state %s unavailable', state)
        return {}
    return {str(c['id']): c['nome'] for c in cities}


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


def _code_by_name(name: str, names: dict[str, str], incomplete: bool) -> str:
    wanted = _plain(name)
    found = [code for code, n in names.items() if _plain(n) == wanted]
    if not found and incomplete:
        raise SourceError(
            'A lista de municípios do IBGE não respondeu; não dá para achar '
            f"'{name}' pelo nome. Tente de novo ou {IBGE_CODE_HINT.lower()}"
        )
    if not found:
        raise AnalysisError(
            f"Município '{name}' não encontrado em {_states_label(STATES)}. "
            + IBGE_CODE_HINT
        )
    if len(found) > 1:
        options = ', '.join(f'{_states_label([c[:2]])}: {c}' for c in found)
        raise AnalysisError(
            f"Há mais de um município '{name}' ({options}). " + IBGE_CODE_HINT
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


def find_city(
    points: list[LonLat], name: str | None = None, code: str | None = None
) -> City:
    """The city by IBGE code, else by name (MG and SP), else the one with
    most of the route vertices (MG first, then SP).

    Raises AnalysisError (city not found) or SourceError (IBGE down).
    """
    # A city code starts with its state code
    states = [code[:2]] if code else list(STATES)
    names, incomplete = {}, False
    for state in states:
        state_names = _city_names(state)
        names.update(state_names)
        incomplete = incomplete or not state_names
    if not code and name:
        code = _code_by_name(name, names, incomplete)
        states = [code[:2]]

    failures = []
    if code:
        try:
            return City(
                code,
                names.get(code, name or code),
                _city_mesh(code),
                CITY_MESH_SOURCE,
            )
        except Exception as error:
            failures.append(f'IBGE malha municipal: {_describe(error)}')
            logger.warning('IBGE city mesh unavailable: %s', error)

    # (route vertices inside, feature, source) of the best city found
    chosen = None
    for state in states:
        sample = 0
        for url, source in STATE_MESH_SOURCES:
            label = f'{source} {_states_label([state])}'
            try:
                features = json.loads(fetch(url.format(state=state)))[
                    'features'
                ]
            except Exception as error:
                failures.append(f'{label}: {_describe(error)}')
                logger.warning('%s unavailable: %s', label, error)
                continue
            if code:
                feature = next(
                    (
                        f
                        for f in features
                        if _feature_code(f.get('properties') or {}) == code
                    ),
                    None,
                )
                if feature is None:
                    failures.append(
                        f'{label}: município {code} não está na malha'
                    )
                    continue
                inside = 0
            else:
                feature, inside, sample = _most_points(features, points)
            if chosen is None or inside > chosen[0]:
                chosen = (inside, feature, source)
            break
        # By the routes, the next state is tried only when most of the route
        # is outside the best city of this one
        if chosen and (code or 2 * chosen[0] > sample):
            break
    if chosen is None:
        raise SourceError(
            'Não consegui o limite do município em nenhuma fonte ('
            + '; '.join(failures)
            + ').'
        )

    _, feature, source = chosen
    props = feature.get('properties') or {}
    found_code = _feature_code(props)
    found_name = names.get(found_code) or _feature_name(props) or found_code
    if not code:
        logger.info(
            'city detected by the routes: %s (%s)', found_name, found_code
        )
        # Prefer the best quality boundary of the detected city
        try:
            return City(
                found_code,
                found_name,
                _city_mesh(found_code),
                CITY_MESH_SOURCE,
            )
        except Exception:
            logger.warning('IBGE city mesh of %s unavailable', found_code)
    return City(
        found_code, found_name, Area(_polygons(feature['geometry'])), source
    )


def _describe(error: Exception) -> str:
    return f'{type(error).__name__}: {error}'
