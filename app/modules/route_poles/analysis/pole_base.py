"""Pole bases: the BDGD (ANEEL) poles of each utility, as Web Mercator tiles.

Each base is a .tar.gz with manifest.json and <version>/<tx>/<ty>.bin files,
one per non-empty zoom 13 tile. Each pole takes 4 bytes: little-endian Uint16
x, y of its position inside the tile.
"""

import json
import logging
import math
import re
import struct
import tarfile
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..constants import CEMIG_RELEASE, EXTRA_RELEASE
from .geometry import LonLat
from .http import download

logger = logging.getLogger(__name__)

# min_lon, min_lat, max_lon, max_lat
Box = tuple[float, float, float, float]

TILE_ZOOM = 13
TILE_N = 2**TILE_ZOOM
TILE_STEPS = 65536
POLE_BYTES = 4
TILE_PATH = re.compile(r'(?:^|/)(\d+)/(\d+)\.bin$')

CEMIG_URL = (
    'https://github.com/VinnyByn/ROUTE-MAP/releases/download/'
    f'{CEMIG_RELEASE}/postes.tar.gz'
)
EXTRA_URL = (
    'https://github.com/Master-Projetos/Master-API/releases/download/'
    f'{EXTRA_RELEASE}/{{asset}}'
)
DOWNLOAD_TIMEOUT_SECONDS = 600


@dataclass(frozen=True)
class PoleBase:
    utility: str
    url: str
    # File name in the cache; it carries the release, so a new one is fetched
    cache_name: str
    # Release asset name, for the bases this repository publishes
    asset: str | None = None


def _extra(utility: str, asset: str) -> PoleBase:
    return PoleBase(
        utility,
        EXTRA_URL.format(asset=asset),
        f'{EXTRA_RELEASE}_{asset}',
        asset,
    )


POLE_BASES = (
    PoleBase('Cemig-D', CEMIG_URL, f'{CEMIG_RELEASE}.tar.gz'),
    _extra('DME', 'postes-dme.tar.gz'),
    _extra('EDP SP', 'postes-edp-sp.tar.gz'),
    _extra('Elektro', 'postes-elektro.tar.gz'),
)

# ~36 MB in all, downloaded on the first analysis; the app folder may be
# read-only in the cloud, so they are cached in the temp dir
CACHE_DIR = Path(tempfile.gettempdir()) / 'cache_postes'
# Two first analyses at once would write the same download files
_download_lock = threading.Lock()


def local_bases(cache_dir: Path = CACHE_DIR) -> list[tuple[PoleBase, Path]]:
    """Every base in POLE_BASES, downloading the missing ones.

    Raises OSError when a download fails.
    """
    with _download_lock:
        cache_dir.mkdir(parents=True, exist_ok=True)
        bases = []
        for base in POLE_BASES:
            path = cache_dir / base.cache_name
            if not path.exists():
                logger.info('downloading pole base %s', base.cache_name)
                download(base.url, path, timeout=DOWNLOAD_TIMEOUT_SECONDS)
            bases.append((base, path))
        return bases


def lon_to_tile_x(lon: float) -> float:
    return (lon + 180) / 360 * TILE_N


def lat_to_tile_y(lat: float) -> float:
    r = math.radians(lat)
    return (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * TILE_N


def tile_x_to_lon(x: float) -> float:
    return x / TILE_N * 360 - 180


def tile_y_to_lat(y: float) -> float:
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / TILE_N))))


def decode_tile(tx: int, ty: int, data: bytes) -> list[LonLat]:
    """The poles of a tile, each position once: the BDGD has some poles
    twice, at the very same point.
    """
    positions = dict.fromkeys(
        struct.unpack_from('<HH', data, i)
        for i in range(0, len(data) - POLE_BYTES + 1, POLE_BYTES)
    )
    return [
        (
            tile_x_to_lon(tx + (qx + 0.5) / TILE_STEPS),
            tile_y_to_lat(ty + (qy + 0.5) / TILE_STEPS),
        )
        for qx, qy in positions
    ]


def tile_range(bbox: Box) -> tuple[int, int, int, int]:
    """(x0, x1, y0, y1) of the tiles crossing bbox."""
    min_lon, min_lat, max_lon, max_lat = bbox
    return (
        int(lon_to_tile_x(min_lon)),
        int(lon_to_tile_x(max_lon)),
        int(lat_to_tile_y(max_lat)),
        int(lat_to_tile_y(min_lat)),
    )


def read_poles(
    path: Path, boxes: list[Box], collect: Callable[[list[LonLat]], None]
) -> dict:
    """Gives collect the poles of each tile crossing any of the boxes, one
    tile at a time (a base has millions of poles, most outside the boxes).
    Returns the manifest of the base .tar.gz.
    """
    ranges = [tile_range(box) for box in boxes]
    manifest = {}
    with tarfile.open(path, 'r:*') as tar:
        for member in tar:
            if not member.isfile():
                continue
            if member.name.endswith('manifest.json'):
                manifest = json.load(tar.extractfile(member))
                continue
            match = TILE_PATH.search(member.name)
            if not match:
                continue
            tx, ty = int(match.group(1)), int(match.group(2))
            if any(
                x0 <= tx <= x1 and y0 <= ty <= y1 for x0, x1, y0, y1 in ranges
            ):
                collect(decode_tile(tx, ty, tar.extractfile(member).read()))
    return manifest
