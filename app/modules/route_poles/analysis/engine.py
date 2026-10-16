"""Crosses the cables with the poles: near poles, length and overlap.

Every cable is cut into ~1 m pieces. A piece counts in the length without
overlap unless an earlier cable (in file order) already covers it:
- it is within DUPLICATE_M of an earlier cable, or
- it runs alongside an earlier cable (within PARALLEL_M, almost parallel)
  and both are nearest to the same pole: the same pole line drawn twice.
  Cables on the two sides of a street hang on different poles, so they
  both count.
"""

import math
from collections import defaultdict
from dataclasses import dataclass, field
from enum import StrEnum

from ..constants import DUPLICATE_M, NO_POLE_M, PARALLEL_COS, PARALLEL_M
from .geometry import XY, Grid, LocalProjection, segment_distance, vincenty
from .routes import Cable

# Poles this far from a cable are mostly across the street: their density
# estimates how many of the near poles are on the other side
BACKSIDE_FROM_M, BACKSIDE_TO_M = 12, 20
POLE_GRID_CELL_M = 25.0
# Keep every n-th piece of the earlier cables, enough for each tolerance
DUPLICATE_SAMPLE_STEP = 2
PARALLEL_SAMPLE_STEP = 4
# Pieces closer than this are the same point (joined in the overlap KMZ)
SAME_POINT_M = 1e-6


class StretchStatus(StrEnum):
    COUNTED = 'contado'
    NO_POLE = 'sem_poste'
    OVERLAP = 'sobreposto'


@dataclass
class Stretch:
    """Consecutive pieces of a cable with the same status (overlap KMZ)."""

    cable: str
    status: StretchStatus
    points: list[XY]
    length_m: float


@dataclass
class RouteResult:
    # pole index -> distance to the nearest cable, for the poles near one
    min_distance: dict[int, float]
    near_poles: list[int]
    total_m: float
    unique_m: float
    # Part of unique_m with no pole closer than NO_POLE_M
    no_pole_m: float
    # Poles per meter of distance between BACKSIDE_FROM_M and BACKSIDE_TO_M
    backside_per_m: float
    stretches: list[Stretch] = field(default_factory=list)


@dataclass
class _Piece:
    x: float
    y: float
    length: float
    # direction
    ux: float
    uy: float
    # ends, for the overlap KMZ
    start: XY
    end: XY


def _pieces(xy: list[XY]) -> list[_Piece]:
    pieces = []
    for (ax, ay), (bx, by) in zip(xy, xy[1:]):
        length = math.hypot(bx - ax, by - ay)
        n = max(1, round(length))
        ux, uy = ((bx - ax) / length, (by - ay) / length) if length else (0, 0)
        for k in range(n):
            t0, t, t1 = k / n, (k + 0.5) / n, (k + 1) / n
            pieces.append(
                _Piece(
                    ax + t * (bx - ax),
                    ay + t * (by - ay),
                    length / n,
                    ux,
                    uy,
                    (ax + t0 * (bx - ax), ay + t0 * (by - ay)),
                    (ax + t1 * (bx - ax), ay + t1 * (by - ay)),
                )
            )
    return pieces


class _CoveredRoute:
    """Pieces of the cables already measured, to detect overlap."""

    def __init__(self, poles: Grid):
        self.poles = poles
        self.near: dict[tuple[int, int], list[XY]] = defaultdict(list)
        # (x, y, ux, uy, nearest pole)
        self.parallel: dict[tuple[int, int], list[tuple]] = defaultdict(list)

    def covers(self, piece: _Piece) -> bool:
        return self._duplicate(piece) or self._parallel(piece)

    def _duplicate(self, piece: _Piece) -> bool:
        gx, gy = int(piece.x // DUPLICATE_M), int(piece.y // DUPLICATE_M)
        return any(
            math.hypot(qx - piece.x, qy - piece.y) <= DUPLICATE_M
            for ix in (-1, 0, 1)
            for iy in (-1, 0, 1)
            for qx, qy in self.near.get((gx + ix, gy + iy), ())
        )

    def _parallel(self, piece: _Piece) -> bool:
        pole = None
        gx, gy = int(piece.x // PARALLEL_M), int(piece.y // PARALLEL_M)
        for ix in (-1, 0, 1):
            for iy in (-1, 0, 1):
                for qx, qy, vx, vy, q_pole in self.parallel.get(
                    (gx + ix, gy + iy), ()
                ):
                    if (
                        math.hypot(qx - piece.x, qy - piece.y) <= PARALLEL_M
                        and abs(piece.ux * vx + piece.uy * vy) >= PARALLEL_COS
                    ):
                        if pole is None:
                            pole = self.poles.nearest_index(
                                piece.x, piece.y, NO_POLE_M
                            )
                        if pole >= 0 and pole == q_pole:
                            return True
        return False

    def add(self, pieces: list[_Piece]) -> None:
        for p in pieces[::DUPLICATE_SAMPLE_STEP]:
            cell = int(p.x // DUPLICATE_M), int(p.y // DUPLICATE_M)
            self.near[cell].append((p.x, p.y))
        for p in pieces[::PARALLEL_SAMPLE_STEP]:
            cell = int(p.x // PARALLEL_M), int(p.y // PARALLEL_M)
            pole = self.poles.nearest_index(p.x, p.y, NO_POLE_M)
            self.parallel[cell].append((p.x, p.y, p.ux, p.uy, pole))


def _add_stretch(
    stretches: list[Stretch],
    cable: str,
    status: StretchStatus,
    piece: _Piece,
    length: float,
) -> None:
    """Joins consecutive pieces of the same cable and status."""
    last = stretches[-1] if stretches else None
    if (
        last
        and last.cable == cable
        and last.status == status
        and math.dist(last.points[-1], piece.start) < SAME_POINT_M
    ):
        last.points.append(piece.end)
        last.length_m += length
    else:
        stretches.append(
            Stretch(cable, status, [piece.start, piece.end], length)
        )


def analyze(
    cables: list[Cable],
    poles: list[tuple[float, float]],
    radius_m: float,
    with_stretches: bool = False,
) -> RouteResult:
    """Fills each cable's lengths and near poles, in place."""
    vertices = [p for c in cables for line in c.lines for p in line]
    projection = LocalProjection(
        sum(p[0] for p in vertices) / len(vertices),
        sum(p[1] for p in vertices) / len(vertices),
    )
    pole_xy = [projection(*p) for p in poles]
    pole_grid = Grid(pole_xy, POLE_GRID_CELL_M)
    search = max(radius_m, BACKSIDE_TO_M + 1.0, NO_POLE_M)
    covered = _CoveredRoute(pole_grid)
    stretches: list[Stretch] = []
    min_distance: dict[int, float] = {}
    total = unique = unique_no_pole = 0.0

    for cable in cables:
        near: dict[int, float] = {}
        geodesic = 0.0
        pieces: list[_Piece] = []
        for line in cable.lines:
            for (lon1, lat1), (lon2, lat2) in zip(line, line[1:]):
                geodesic += vincenty(lon1, lat1, lon2, lat2)
            xy = [projection(*p) for p in line]
            for (ax, ay), (bx, by) in zip(xy, xy[1:]):
                for i in pole_grid.near(
                    min(ax, bx) - search,
                    min(ay, by) - search,
                    max(ax, bx) + search,
                    max(ay, by) + search,
                ):
                    d = segment_distance(*pole_xy[i], ax, ay, bx, by)
                    if d <= search and d < near.get(i, math.inf):
                        near[i] = d
            pieces += _pieces(xy)

        # Corrects the planar length to the geodesic one
        scale = geodesic / (sum(p.length for p in pieces) or 1.0)
        no_pole = cable_unique = 0.0
        for piece in pieces:
            length = piece.length * scale
            far = (
                pole_grid.nearest_distance(piece.x, piece.y, NO_POLE_M)
                > NO_POLE_M
            )
            if far:
                no_pole += length
            overlap = covered.covers(piece)
            if not overlap:
                cable_unique += length
                if far:
                    unique_no_pole += length
            if with_stretches:
                status = (
                    StretchStatus.OVERLAP
                    if overlap
                    else StretchStatus.NO_POLE
                    if far
                    else StretchStatus.COUNTED
                )
                _add_stretch(stretches, cable.name, status, piece, length)
        covered.add(pieces)

        cable.length_m, cable.unique_length_m = geodesic, cable_unique
        cable.no_pole_m, cable.near = no_pole, near
        total += geodesic
        unique += cable_unique
        for i, d in near.items():
            if d < min_distance.get(i, math.inf):
                min_distance[i] = d

    for stretch in stretches:
        stretch.points = [projection.inverse(*p) for p in stretch.points]
    backside = sum(
        1
        for d in min_distance.values()
        if BACKSIDE_FROM_M <= d < BACKSIDE_TO_M
    ) / (BACKSIDE_TO_M - BACKSIDE_FROM_M)
    return RouteResult(
        min_distance=min_distance,
        near_poles=sorted(i for i, d in min_distance.items() if d <= radius_m),
        total_m=total,
        unique_m=unique,
        no_pole_m=unique_no_pole,
        backside_per_m=backside,
        stretches=stretches,
    )
