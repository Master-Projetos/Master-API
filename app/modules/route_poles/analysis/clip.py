"""Cuts cables at the border of a city."""

import math

from .city import Area
from .geometry import LonLat
from .routes import Cable

# Sampling step (degrees, ~11 m) and precision of the cut at a city border
CLIP_STEP = 1e-4
CLIP_BISECTIONS = 30

Line = list[LonLat]


def clip_cables(cables: list[Cable], area: Area) -> list[Cable]:
    """The stretch of each cable inside the area; none outside is kept."""
    return [
        Cable(cable.folder, cable.name, cable.cable_type, lines)
        for cable in cables
        if (lines := clip_lines(cable.lines, area))
    ]


def clip_lines(lines: list[Line], area: Area) -> list[Line]:
    """The parts of the lines inside the area, cut at its border."""
    clipped: list[Line] = []
    for line in lines:
        current: Line = []
        for a, b in zip(line, line[1:]):
            steps = max(1, math.ceil(math.dist(a, b) / CLIP_STEP))
            points = [
                (
                    a[0] + (b[0] - a[0]) * k / steps,
                    a[1] + (b[1] - a[1]) * k / steps,
                )
                for k in range(steps + 1)
            ]
            inside = [area.contains(*p) for p in points]
            if not current and inside[0]:
                current.append(a)
            for k in range(steps):
                if inside[k] == inside[k + 1]:
                    continue
                cut = border_point(area, points[k], points[k + 1], inside[k])
                if inside[k]:
                    current.append(cut)
                    if len(current) > 1:
                        clipped.append(current)
                    current = []
                else:
                    current = [cut]
            if inside[-1]:
                current.append(b)
        if len(current) > 1:
            clipped.append(current)
    # A line that only touches the border leaves a piece with no length
    return [line for line in clipped if len(set(line)) > 1]


def border_point(area: Area, p: LonLat, q: LonLat, p_inside: bool) -> LonLat:
    """Where the segment p-q crosses the border, by bisection."""
    inside, outside = (p, q) if p_inside else (q, p)
    for _ in range(CLIP_BISECTIONS):
        mid = ((inside[0] + outside[0]) / 2, (inside[1] + outside[1]) / 2)
        if area.contains(*mid):
            inside = mid
        else:
            outside = mid
    return inside
