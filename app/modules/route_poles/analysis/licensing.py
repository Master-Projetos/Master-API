"""The licensed poles crossed with the poles in use.

A licensed marker and a pole in use are the same pole when they are within
MATCH_TOLERANCE_M (any number of each), or, among the ones that matched
nothing, one to one and the closest first within DISPLACED_POLE_M: the BDGD
puts some poles off. A licensed marker is in use when it is a pole in use,
when a cable is near it or when it sits between two licensed markers in use;
a pole in use that is no licensed marker is unlicensed. The counts add up
only per side: matched + unused is the licensed poles and matched poles in
use + unlicensed is the poles in use.
"""

import json
import math
import zlib
from collections import defaultdict
from dataclasses import dataclass

from ..constants import (
    DISPLACED_POLE_M,
    MATCH_TOLERANCE_M,
    SEQUENCE_MAX_COS,
    SEQUENCE_SPAN_M,
)
from .city import City
from .geometry import XY, Grid, LocalProjection, LonLat, segment_distance
from .kmz import PointGroup, points_kmz
from .routes import Cable, Marker

Lines = list[list[LonLat]]
COORDINATE_DECIMALS = 7

# KML colors (aabbggrr)
MATCHED_COLOR = 'ff00ff00'
SEQUENCE_COLOR = 'ff90ee90'
UNLICENSED_COLOR = 'ff0000ff'
UNUSED_COLOR = 'ff00a5ff'
PENDING_COLOR = 'ffb4b4b4'
OUTSIDE_COLOR = 'ffffffff'


@dataclass(frozen=True)
class CityComparison:
    """The licensed markers in use are in one list each, by the first reason
    in this order, and keep the licensed position.
    """

    # With the distance to the pole in use
    by_pole: list[tuple[Marker, float]]
    by_cable: list[Marker]
    # Between two licensed markers in use by pole or cable
    by_sequence: list[Marker]
    # Poles in use that are no licensed marker
    unlicensed: list[LonLat]
    unused: list[Marker]
    used_poles: int

    @property
    def matched(self) -> list[Marker]:
        return [
            *(marker for marker, _ in self.by_pole),
            *self.by_cable,
            *self.by_sequence,
        ]


def assign_markers(
    markers: list[Marker], cities: list[City]
) -> tuple[list[list[Marker]], list[Marker]]:
    """The markers inside each city, in the order of the cities (a marker
    inside two goes to the first), and the ones inside none.
    """
    inside: list[list[Marker]] = [[] for _ in cities]
    outside = []
    for marker in markers:
        lon, lat, _ = marker
        for k, city in enumerate(cities):
            x0, y0, x1, y1 = city.area.bbox
            if (
                x0 <= lon <= x1
                and y0 <= lat <= y1
                and city.area.contains(lon, lat)
            ):
                inside[k].append(marker)
                break
        else:
            outside.append(marker)
    return inside, outside


def projected(*groups: list[LonLat]) -> list[list[XY]]:
    """Each group in planar meters, around the center of them all."""
    points = [p for group in groups for p in group]
    if not points:
        return [[] for _ in groups]
    projection = LocalProjection(
        sum(p[0] for p in points) / len(points),
        sum(p[1] for p in points) / len(points),
    )
    return [[projection(*p) for p in group] for group in groups]


def nearest_within(
    points: list[XY], others: list[XY], tolerance_m: float
) -> dict[int, float]:
    """For each point with one of the others within the tolerance, the
    distance to the nearest of them. A point can be near any number of
    others.
    """
    grid = Grid(others, tolerance_m)
    near = {}
    for i, (x, y) in enumerate(points):
        distance = grid.nearest_distance(x, y, tolerance_m)
        if distance <= tolerance_m:
            near[i] = distance
    return near


def poles_near(
    poles: list[LonLat],
    others: list[LonLat],
    tolerance_m: float = MATCH_TOLERANCE_M,
) -> set[int]:
    """The indexes of the poles that have one of the others within the
    tolerance.
    """
    if not poles or not others:
        return set()
    return set(nearest_within(*projected(poles, others), tolerance_m))


def pair_nearest(
    points: dict[int, XY], others: dict[int, XY], tolerance_m: float
) -> dict[int, tuple[int, float]]:
    """One to one, the closest pairs first: point index -> (other index,
    distance), for the points paired within the tolerance.
    """
    keys = list(others)
    grid = Grid([others[key] for key in keys], tolerance_m)
    candidates = []
    for i, (x, y) in points.items():
        for k in grid.near(
            x - tolerance_m, y - tolerance_m, x + tolerance_m, y + tolerance_m
        ):
            ox, oy = others[keys[k]]
            distance = math.hypot(ox - x, oy - y)
            if distance <= tolerance_m:
                candidates.append((distance, i, keys[k]))
    pairs: dict[int, tuple[int, float]] = {}
    taken = set()
    for distance, i, j in sorted(candidates):
        if i not in pairs and j not in taken:
            pairs[i] = (j, distance)
            taken.add(j)
    return pairs


def _cos(a: XY, b: XY) -> float:
    return (a[0] * b[0] + a[1] * b[1]) / (math.hypot(*a) * math.hypot(*b))


def in_sequence(points: list[XY], in_use: list[XY]) -> set[int]:
    """The indexes of the points with two of the in use within
    SEQUENCE_SPAN_M, on opposite sides.
    """
    span = SEQUENCE_SPAN_M
    grid = Grid(in_use, span)
    found = set()
    for i, (x, y) in enumerate(points):
        neighbors = []
        for j in grid.near(x - span, y - span, x + span, y + span):
            vector = (in_use[j][0] - x, in_use[j][1] - y)
            if 0 < math.hypot(*vector) <= span:
                neighbors.append(vector)
        if any(
            _cos(a, b) <= SEQUENCE_MAX_COS
            for k, a in enumerate(neighbors)
            for b in neighbors[k + 1 :]
        ):
            found.add(i)
    return found


def encode_cable_lines(cables: list[Cable]) -> bytes:
    """The vertices of the cables, to store."""
    lines = [
        [
            [round(lon, COORDINATE_DECIMALS), round(lat, COORDINATE_DECIMALS)]
            for lon, lat in line
        ]
        for cable in cables
        for line in cable.lines
    ]
    return zlib.compress(json.dumps(lines, separators=(',', ':')).encode())


def decode_cable_lines(content: bytes) -> Lines:
    return [
        [(lon, lat) for lon, lat in line]
        for line in json.loads(zlib.decompress(content))
    ]


def cables_near(
    markers: list[LonLat], lines: Lines, radius_m: float
) -> set[int]:
    """The indexes of the markers within the radius of a cable (of a segment
    of it, not only of its vertices).
    """
    if not markers or not lines:
        return set()
    projection = LocalProjection(*markers[0])
    segments = defaultdict(list)
    for line in lines:
        xy = [projection(*p) for p in line]
        for (ax, ay), (bx, by) in zip(xy, xy[1:]):
            for gx in range(
                int(min(ax, bx) // radius_m), int(max(ax, bx) // radius_m) + 1
            ):
                for gy in range(
                    int(min(ay, by) // radius_m),
                    int(max(ay, by) // radius_m) + 1,
                ):
                    segments[gx, gy].append((ax, ay, bx, by))
    near = set()
    for i, marker in enumerate(markers):
        x, y = projection(*marker)
        gx, gy = int(x // radius_m), int(y // radius_m)
        if any(
            segment_distance(x, y, *segment) <= radius_m
            for ix in (-1, 0, 1)
            for iy in (-1, 0, 1)
            for segment in segments.get((gx + ix, gy + iy), ())
        ):
            near.add(i)
    return near


def compare_city(
    licensed: list[Marker],
    used: list[LonLat],
    tolerance_m: float = MATCH_TOLERANCE_M,
    cables: list[tuple[Lines, float]] | None = None,
) -> CityComparison:
    """The cables are (lines, radius) pairs, optional: an analysis saved
    before they were kept has none, and its markers are in use only by the
    poles and the sequence.
    """
    positions = [m[:2] for m in licensed]
    licensed_xy, used_xy = projected(positions, used)
    same = nearest_within(licensed_xy, used_xy, tolerance_m)
    used_same = nearest_within(used_xy, licensed_xy, tolerance_m)
    displaced = pair_nearest(
        {i: p for i, p in enumerate(licensed_xy) if i not in same},
        {j: p for j, p in enumerate(used_xy) if j not in used_same},
        DISPLACED_POLE_M,
    )
    by_pole = same | {i: distance for i, (_, distance) in displaced.items()}
    near_cable = set()
    for lines, radius_m in cables or ():
        near_cable |= cables_near(positions, lines, radius_m)
    in_use = by_pole.keys() | near_cable
    rest = [i for i in range(len(licensed)) if i not in in_use]
    sequence = {
        rest[k]
        for k in in_sequence(
            [licensed_xy[i] for i in rest],
            [licensed_xy[i] for i in in_use],
        )
    }
    licensed_used = used_same.keys() | {j for j, _ in displaced.values()}
    return CityComparison(
        by_pole=[
            (m, by_pole[i]) for i, m in enumerate(licensed) if i in by_pole
        ],
        by_cable=[
            m
            for i, m in enumerate(licensed)
            if i in near_cable and i not in by_pole
        ],
        by_sequence=[m for i, m in enumerate(licensed) if i in sequence],
        unlicensed=[p for j, p in enumerate(used) if j not in licensed_used],
        unused=[
            m
            for i, m in enumerate(licensed)
            if i not in in_use and i not in sequence
        ],
        used_poles=len(used),
    )


def comparison_kmz(
    title: str,
    comparisons: list[CityComparison],
    pending: list[Marker],
    outside: list[Marker],
) -> bytes:
    """The mix: the poles of every city by what they are. The licensed and
    the unlicensed ones together are the poles in use, at the licensed
    position wherever there is one.
    """

    def named(markers: list[Marker]):
        return [(lon, lat, name, '') for lon, lat, name in markers]

    groups: list[PointGroup] = [
        (
            'Licenciado e utilizado',
            MATCHED_COLOR,
            [
                *(
                    (lon, lat, name, f'Poste da BDGD a {distance:.1f} m')
                    for c in comparisons
                    for (lon, lat, name), distance in c.by_pole
                ),
                *(
                    (lon, lat, name, 'Cabo da análise perto')
                    for c in comparisons
                    for lon, lat, name in c.by_cable
                ),
            ],
        ),
        (
            'Licenciado entre outros em uso',
            SEQUENCE_COLOR,
            [
                (lon, lat, name, 'Entre dois licenciados em uso')
                for c in comparisons
                for lon, lat, name in c.by_sequence
            ],
        ),
        (
            'Utilizado sem licença',
            UNLICENSED_COLOR,
            [
                (
                    lon,
                    lat,
                    '',
                    'Poste da BDGD sem licenciado a até '
                    f'{DISPLACED_POLE_M:g} m',
                )
                for c in comparisons
                for lon, lat in c.unlicensed
            ],
        ),
        (
            'Licenciado sem uso',
            UNUSED_COLOR,
            named([m for c in comparisons for m in c.unused]),
        ),
        (
            'Licenciado, aguardando cabos da cidade',
            PENDING_COLOR,
            named(pending),
        ),
        (
            'Licenciado fora das cidades de MG e SP',
            OUTSIDE_COLOR,
            named(outside),
        ),
    ]
    return points_kmz(title, groups)
