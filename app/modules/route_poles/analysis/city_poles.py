"""The poles inside each city, from every utility pole base."""

from array import array
from dataclasses import dataclass

from ..constants import BASE_MIN_SHARE
from .city import City
from .errors import AnalysisError
from .geometry import LonLat
from .pole_base import POLE_BASES, Box, local_bases, read_poles

# Margin (degrees) around the cities when reading the pole tiles
BBOX_MARGIN = 0.001


@dataclass(frozen=True)
class CityPoles:
    # lon, lat, lon, lat...: 16 bytes a pole instead of ~100 as a tuple
    coords: array
    # e.g. 'BDGD Cemig-D 2025-12-31'; empty when no base has poles here
    base_label: str

    @property
    def count(self) -> int:
        return len(self.coords) // 2

    @property
    def poles(self) -> list[LonLat]:
        """A new list on each call: keep it only while analysing the city."""
        return list(zip(self.coords[::2], self.coords[1::2]))


def poles_in_cities(cities: list[City]) -> list[CityPoles]:
    """The poles inside each city, in the order of the cities.

    A pole inside more than one city counts for the first. A city on a border
    may have poles from more than one utility: the label lists the ones with
    a meaningful share.
    """
    boxes = [_padded(city.area.bbox) for city in cities]
    coords = [array('d') for _ in cities]
    found: list[list[tuple[int, str, str | None]]] = [[] for _ in cities]
    for base, path in local_bases():
        counts = [0] * len(cities)

        def assign(tile_poles: list[LonLat]) -> None:
            for pole in tile_poles:
                for k, city in enumerate(cities):
                    if city.area.contains(*pole):
                        coords[k].extend(pole)
                        counts[k] += 1
                        break

        manifest = read_poles(path, boxes, assign)
        for k, count in enumerate(counts):
            if count:
                found[k].append((
                    count,
                    base.utility,
                    manifest.get('data_base'),
                ))
    return [
        CityPoles(city_coords, _base_label(len(city_coords) // 2, city_found))
        for city_coords, city_found in zip(coords, found)
    ]


def no_poles_error(where: str) -> AnalysisError:
    utilities = ', '.join(base.utility for base in POLE_BASES)
    return AnalysisError(
        f'No poles from the pole bases ({utilities}) in {where} '
        "(another utility's area?)."
    )


def _padded(bbox: Box) -> Box:
    return (
        bbox[0] - BBOX_MARGIN,
        bbox[1] - BBOX_MARGIN,
        bbox[2] + BBOX_MARGIN,
        bbox[3] + BBOX_MARGIN,
    )


def _base_label(total: int, found: list[tuple[int, str, str | None]]) -> str:
    return ' + '.join(
        ' '.join(filter(None, ('BDGD', utility, data_base)))
        for count, utility, data_base in found
        if count >= BASE_MIN_SHARE * total
    )
