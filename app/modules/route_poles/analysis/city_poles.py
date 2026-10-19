"""The poles inside each city, from every utility pole base."""

from dataclasses import dataclass

from ..constants import BASE_MIN_SHARE
from .city import City
from .errors import AnalysisError
from .geometry import LonLat
from .pole_base import POLE_BASES, local_bases, read_poles

# Margin (degrees) around the cities and routes when reading the pole tiles
BBOX_MARGIN = 0.001


@dataclass(frozen=True)
class CityPoles:
    poles: list[LonLat]
    # e.g. 'BDGD Cemig-D 2025-12-31'; empty when no base has poles here
    base_label: str


def poles_in_cities(
    cities: list[City], vertices: list[LonLat]
) -> list[CityPoles]:
    """The poles inside each city, in the order of the cities.

    A pole inside more than one city counts for the first. A city on a border
    may have poles from more than one utility: the label lists the ones with
    a meaningful share.
    """
    bbox = _bbox(cities, vertices)
    poles: list[list[LonLat]] = [[] for _ in cities]
    found: list[list[tuple[int, str, str | None]]] = [[] for _ in cities]
    for base, path in local_bases():
        base_poles, manifest = read_poles(path, bbox)
        counts = [0] * len(cities)
        for pole in base_poles:
            for k, city in enumerate(cities):
                if city.area.contains(*pole):
                    poles[k].append(pole)
                    counts[k] += 1
                    break
        for k, count in enumerate(counts):
            if count:
                found[k].append((
                    count,
                    base.utility,
                    manifest.get('data_base'),
                ))
    return [
        CityPoles(city_poles, _base_label(city_poles, city_found))
        for city_poles, city_found in zip(poles, found)
    ]


def no_poles_error(where: str) -> AnalysisError:
    utilities = ', '.join(base.utility for base in POLE_BASES)
    return AnalysisError(
        f'No poles from the pole bases ({utilities}) in {where} '
        "(another utility's area?)."
    )


def _bbox(
    cities: list[City], vertices: list[LonLat]
) -> tuple[float, float, float, float]:
    xs = [p[0] for p in vertices]
    ys = [p[1] for p in vertices]
    for city in cities:
        xs += (city.area.bbox[0], city.area.bbox[2])
        ys += (city.area.bbox[1], city.area.bbox[3])
    return (
        min(xs) - BBOX_MARGIN,
        min(ys) - BBOX_MARGIN,
        max(xs) + BBOX_MARGIN,
        max(ys) + BBOX_MARGIN,
    )


def _base_label(
    poles: list[LonLat], found: list[tuple[int, str, str | None]]
) -> str:
    return ' + '.join(
        ' '.join(filter(None, ('BDGD', utility, data_base)))
        for count, utility, data_base in found
        if count >= BASE_MIN_SHARE * len(poles)
    )
