"""The licensed poles crossed with the poles in use.

A licensed marker is in use when a pole in use or a cable is near it, and a
pole in use is licensed when a licensed marker is near it. Neither side is
exclusive, so the counts add up only per side: matched + unused is the
licensed poles and unlicensed is the poles in use that no marker is near.
"""

import json
import math
import zlib
from collections import defaultdict
from dataclasses import dataclass

from ..constants import MATCH_TOLERANCE_M
from .city import City
from .geometry import Grid, LocalProjection, LonLat, segment_distance
from .kmz import PointGroup, points_kmz
from .routes import Cable, Marker

Lines = list[list[LonLat]]
COORDINATE_DECIMALS = 7

# KML colors (aabbggrr)
MATCHED_COLOR = 'ff00ff00'
UNLICENSED_COLOR = 'ff0000ff'
UNUSED_COLOR = 'ff00a5ff'
PENDING_COLOR = 'ffb4b4b4'
OUTSIDE_COLOR = 'ffffffff'


@dataclass(frozen=True)
class CityComparison:
    # Licensed markers with a pole in use or a cable near, at the licensed
    # position
    matched: list[Marker]
    # Poles in use with no licensed marker near
    unlicensed: list[LonLat]
    # Licensed markers with no pole in use and no cable near
    unused: list[Marker]
    used_poles: int


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


def poles_near(
    poles: list[LonLat],
    others: list[LonLat],
    tolerance_m: float = MATCH_TOLERANCE_M,
) -> set[int]:
    """The indexes of the poles that have one of the others within the
    tolerance. A pole can be near any number of others.
    """
    if not poles or not others:
        return set()
    points = [*poles, *others]
    projection = LocalProjection(
        sum(p[0] for p in points) / len(points),
        sum(p[1] for p in points) / len(points),
    )
    others_xy = [projection(*p) for p in others]
    grid = Grid(others_xy, tolerance_m)
    near = set()
    for i, pole in enumerate(poles):
        x, y = projection(*pole)
        if any(
            math.hypot(others_xy[j][0] - x, others_xy[j][1] - y) <= tolerance_m
            for j in grid.near(
                x - tolerance_m,
                y - tolerance_m,
                x + tolerance_m,
                y + tolerance_m,
            )
        ):
            near.add(i)
    return near


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
    poles.
    """
    positions = [m[:2] for m in licensed]
    in_use = poles_near(positions, used, tolerance_m)
    for lines, radius_m in cables or ():
        in_use |= cables_near(positions, lines, radius_m)
    licensed_used = poles_near(used, positions, tolerance_m)
    return CityComparison(
        matched=[m for i, m in enumerate(licensed) if i in in_use],
        unlicensed=[p for j, p in enumerate(used) if j not in licensed_used],
        unused=[m for i, m in enumerate(licensed) if i not in in_use],
        used_poles=len(used),
    )


def comparison_kmz(
    title: str,
    comparisons: list[CityComparison],
    pending: list[Marker],
    outside: list[Marker],
) -> bytes:
    """The mix: the poles of every city by what they are."""
    groups: list[PointGroup] = [
        (
            'Licenciado e utilizado',
            MATCHED_COLOR,
            [m for c in comparisons for m in c.matched],
        ),
        (
            'Utilizado sem licença',
            UNLICENSED_COLOR,
            [
                (*p, 'Poste utilizado sem licença')
                for c in comparisons
                for p in c.unlicensed
            ],
        ),
        (
            'Licenciado sem uso',
            UNUSED_COLOR,
            [m for c in comparisons for m in c.unused],
        ),
        ('Licenciado, aguardando cabos da cidade', PENDING_COLOR, pending),
        ('Licenciado fora das cidades de MG e SP', OUTSIDE_COLOR, outside),
    ]
    return points_kmz(title, groups)
