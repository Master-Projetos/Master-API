import math
from collections import defaultdict
from collections.abc import Iterator

# WGS 84
EARTH_A = 6378137.0
EARTH_F = 1 / 298.257223563
EARTH_E2 = 0.00669437999014
EARTH_MEAN_RADIUS = 6371008.8
VINCENTY_ITERATIONS = 200
VINCENTY_TOLERANCE = 1e-12

LonLat = tuple[float, float]
XY = tuple[float, float]


def vincenty(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Geodesic distance in meters (WGS 84 ellipsoid)."""
    a, f = EARTH_A, EARTH_F
    b = a * (1 - f)
    lon_diff = math.radians(lon2 - lon1)
    u1 = math.atan((1 - f) * math.tan(math.radians(lat1)))
    u2 = math.atan((1 - f) * math.tan(math.radians(lat2)))
    sin_u1, cos_u1 = math.sin(u1), math.cos(u1)
    sin_u2, cos_u2 = math.sin(u2), math.cos(u2)
    lam = lon_diff
    for _ in range(VINCENTY_ITERATIONS):
        sin_lam, cos_lam = math.sin(lam), math.cos(lam)
        sin_sigma = math.hypot(
            cos_u2 * sin_lam, cos_u1 * sin_u2 - sin_u1 * cos_u2 * cos_lam
        )
        if sin_sigma == 0:
            return 0.0
        cos_sigma = sin_u1 * sin_u2 + cos_u1 * cos_u2 * cos_lam
        sigma = math.atan2(sin_sigma, cos_sigma)
        sin_alpha = cos_u1 * cos_u2 * sin_lam / sin_sigma
        cos2_alpha = 1 - sin_alpha * sin_alpha
        cos_2sm = (
            cos_sigma - 2 * sin_u1 * sin_u2 / cos2_alpha if cos2_alpha else 0.0
        )
        c = f / 16 * cos2_alpha * (4 + f * (4 - 3 * cos2_alpha))
        previous = lam
        lam = lon_diff + (1 - c) * f * sin_alpha * (
            sigma
            + c
            * sin_sigma
            * (cos_2sm + c * cos_sigma * (-1 + 2 * cos_2sm * cos_2sm))
        )
        if abs(lam - previous) < VINCENTY_TOLERANCE:
            break
    else:
        # Antipodal points never converge: haversine is close enough
        p1, p2 = math.radians(lat1), math.radians(lat2)
        h = (
            math.sin((p2 - p1) / 2) ** 2
            + math.cos(p1) * math.cos(p2) * math.sin(lon_diff / 2) ** 2
        )
        return 2 * EARTH_MEAN_RADIUS * math.asin(math.sqrt(h))
    u_sq = cos2_alpha * (a * a - b * b) / (b * b)
    big_a = 1 + u_sq / 16384 * (
        4096 + u_sq * (-768 + u_sq * (320 - 175 * u_sq))
    )
    big_b = u_sq / 1024 * (256 + u_sq * (-128 + u_sq * (74 - 47 * u_sq)))
    delta_sigma = (
        big_b
        * sin_sigma
        * (
            cos_2sm
            + big_b
            / 4
            * (
                cos_sigma * (-1 + 2 * cos_2sm * cos_2sm)
                - big_b
                / 6
                * cos_2sm
                * (-3 + 4 * sin_sigma * sin_sigma)
                * (-3 + 4 * cos_2sm * cos_2sm)
            )
        )
    )
    return b * big_a * (sigma - delta_sigma)


class LocalProjection:
    """Planar meters around (lon0, lat0); good at the scale of a city."""

    def __init__(self, lon0: float, lat0: float):
        sin_lat = math.sin(math.radians(lat0))
        w = math.sqrt(1 - EARTH_E2 * sin_lat * sin_lat)
        self.my = math.radians(1) * EARTH_A * (1 - EARTH_E2) / w**3
        self.mx = math.radians(1) * EARTH_A / w * math.cos(math.radians(lat0))
        self.lon0, self.lat0 = lon0, lat0

    def __call__(self, lon: float, lat: float) -> XY:
        return (lon - self.lon0) * self.mx, (lat - self.lat0) * self.my

    def inverse(self, x: float, y: float) -> LonLat:
        return x / self.mx + self.lon0, y / self.my + self.lat0


def segment_distance(
    px: float, py: float, ax: float, ay: float, bx: float, by: float
) -> float:
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    t = (
        0.0
        if length_sq == 0
        else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
    )
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


class Grid:
    """Spatial hash of points, to find the ones near a box quickly."""

    def __init__(self, points: list[XY], cell: float):
        self.cell, self.points = cell, points
        self.cells: dict[tuple[int, int], list[int]] = defaultdict(list)
        for i, (x, y) in enumerate(points):
            self.cells[int(x // cell), int(y // cell)].append(i)

    def near(
        self, x0: float, y0: float, x1: float, y1: float
    ) -> Iterator[int]:
        c = self.cell
        for gx in range(int(x0 // c), int(x1 // c) + 1):
            for gy in range(int(y0 // c), int(y1 // c) + 1):
                yield from self.cells.get((gx, gy), ())

    def nearest_distance(self, x: float, y: float, limit: float) -> float:
        """Distance to the nearest point; inf when none is within limit."""
        best = math.inf
        for i in self.near(x - limit, y - limit, x + limit, y + limit):
            px, py = self.points[i]
            best = min(best, math.hypot(px - x, py - y))
        return best

    def nearest_index(self, x: float, y: float, limit: float) -> int:
        """Index of the nearest point within limit, -1 when none."""
        best, best_index = limit, -1
        for i in self.near(x - limit, y - limit, x + limit, y + limit):
            px, py = self.points[i]
            distance = math.hypot(px - x, py - y)
            if distance <= best:
                best, best_index = distance, i
        return best_index
