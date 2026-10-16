import io
import logging
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from dataclasses import dataclass, field

from ..constants import (
    CABLE_TYPE_PREFIXES,
    EXCLUDED_CABLE_PREFIXES,
    MAX_KML_BYTES,
    UNKNOWN_CABLE_TYPE,
)
from .errors import AnalysisError
from .geometry import LonLat

logger = logging.getLogger(__name__)

ZIP_MAGIC = b'PK'
# Longest prefix first, so a shorter one can't steal its match
CABLE_TYPE = re.compile(
    r'\s*('
    + '|'.join(
        re.escape(prefix)
        for prefix in sorted(CABLE_TYPE_PREFIXES, key=len, reverse=True)
    )
    + r')[-_ ]?(\d+)',
    re.IGNORECASE,
)
_TYPE_LABELS = {p.upper(): label for p, label in CABLE_TYPE_PREFIXES.items()}
# A KML coordinate is lon,lat[,alt]
MIN_COORDINATES = 2


@dataclass
class Cable:
    folder: str
    name: str
    cable_type: str
    lines: list[list[LonLat]]
    # Filled by engine.analyze()
    length_m: float = 0.0
    unique_length_m: float = 0.0
    no_pole_m: float = 0.0
    # pole index -> distance (m), for the poles near the cable
    near: dict[int, float] = field(default_factory=dict)


def cable_type(name: str) -> str:
    match = CABLE_TYPE.match(name)
    if not match:
        return UNKNOWN_CABLE_TYPE
    label = _TYPE_LABELS[match.group(1).upper()]
    return f'{label}-{int(match.group(2)):02d}'


def excluded_prefix(name: str) -> str | None:
    """The EXCLUDED_CABLE_PREFIXES entry the name starts with, if any."""
    upper = name.strip().upper()
    return next(
        (p for p in EXCLUDED_CABLE_PREFIXES if upper.startswith(p.upper())),
        None,
    )


def kml_bytes(content: bytes) -> bytes:
    """The KML of a KMZ, or the content itself when it is a plain KML."""
    if content[:2] != ZIP_MAGIC:
        return content
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as kmz:
            kmls = [
                i
                for i in kmz.infolist()
                if i.filename.lower().endswith('.kml')
            ]
            if not kmls:
                raise AnalysisError(
                    'O KMZ não tem nenhum arquivo .kml dentro.'
                )
            main = next((i for i in kmls if i.filename == 'doc.kml'), kmls[0])
            if main.file_size > MAX_KML_BYTES:
                raise AnalysisError(
                    f'KML grande demais ({main.file_size / 1e6:.0f} MB '
                    'descompactado).'
                )
            return kmz.read(main)
    except zipfile.BadZipFile:
        raise AnalysisError('Arquivo KMZ corrompido.') from None


def _tag(element) -> str:
    return element.tag.rsplit('}', 1)[-1]


def _child(element, name: str):
    return next((c for c in element if _tag(c) == name), None)


def _text(element, name: str) -> str:
    child = _child(element, name)
    return (child.text or '').strip() if child is not None else ''


def _lines(placemark) -> list[list[LonLat]]:
    lines = []
    for geometry in placemark.iter():
        if _tag(geometry) != 'LineString':
            continue
        points = []
        for token in _text(geometry, 'coordinates').split():
            values = token.split(',')
            if len(values) >= MIN_COORDINATES:
                points.append((float(values[0]), float(values[1])))
        if points:
            lines.append(points)
    return lines


def read_cables(content: bytes) -> list[Cable]:
    """The cables (Placemarks with lines) of a KMZ/KML, in file order.

    The order matters: where cables overlap, the first one keeps the length.
    """
    try:
        root = ET.fromstring(kml_bytes(content))
    except ET.ParseError as error:
        raise AnalysisError(
            f'O arquivo não é um KML válido ({error}).'
        ) from None

    cables = []
    excluded: Counter[str] = Counter()

    def walk(element, folders: list[str]) -> None:
        for child in element:
            tag = _tag(child)
            if tag in {'Document', 'Folder'}:
                walk(child, [*folders, _text(child, 'name')])
            elif tag == 'Placemark':
                name = _text(child, 'name')
                lines = _lines(child)
                if not lines:
                    continue
                if prefix := excluded_prefix(name):
                    excluded[prefix] += 1
                    continue
                # The first level is the document itself
                folder = '/'.join(f for f in folders[1:] if f) or (
                    folders[0] if folders else ''
                )
                cables.append(Cable(folder, name, cable_type(name), lines))

    walk(root, [])
    if excluded:
        logger.info('cables left out by name prefix: %s', dict(excluded))
    return cables
