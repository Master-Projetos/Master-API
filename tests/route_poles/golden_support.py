"""Turns analysis results into plain JSON for the golden files."""

import hashlib
import io
import json
import zipfile
from datetime import date
from pathlib import Path

GOLDEN_DIR = Path(__file__).with_name('golden')
KMZ_FIELDS = (
    'poles_kmz',
    'all_poles_kmz',
    'overlap_kmz',
    'with_overlap_kmz',
    'without_overlap_kmz',
)
DATE_PLACEHOLDER = 'DATE'


MAX_INLINE_CHARS = 3000


def kml_text(kmz: bytes | None) -> str | None:
    if kmz is None:
        return None
    with zipfile.ZipFile(io.BytesIO(kmz)) as archive:
        return archive.read('doc.kml').decode()


def digest(text: str | None):
    """Small texts stay readable; big ones become a hash."""
    if text is None or len(text) <= MAX_INLINE_CHARS:
        return text
    return {
        'length': len(text),
        'sha256': hashlib.sha256(text.encode()).hexdigest(),
    }


def normalize(value):
    """Freezes today's date, so the golden files don't age."""
    return json.loads(
        json.dumps(value).replace(date.today().isoformat(), DATE_PLACEHOLDER)
    )


def describe_data(data, drop=()) -> dict:
    fields = {*KMZ_FIELDS, 'cities', *drop}
    described = data.model_dump(mode='json', exclude=fields)
    described['kmz'] = {
        field: digest(kml_text(getattr(data, field))) for field in KMZ_FIELDS
    }
    return normalize(described)


def describe_city(city) -> dict:
    return {
        'code': city.code,
        'name': city.name,
        'bbox': [round(v, 7) for v in city.area.bbox],
        'polygons': len(city.area.polygons),
    }


def describe_lines(lines) -> list:
    return [[[round(x, 7), round(y, 7)] for x, y in line] for line in lines]


def load_golden(name: str):
    return json.loads((GOLDEN_DIR / f'{name}.json').read_text('utf-8'))


def digest_json(value) -> dict:
    text = json.dumps(value, sort_keys=True)
    return {
        'items': len(value),
        'sha256': hashlib.sha256(text.encode()).hexdigest(),
    }


def describe_engine(cables, result) -> dict:
    """The engine output; the big collections are hashed."""
    by_status: dict[str, list] = {}
    for stretch in result.stretches:
        entry = by_status.setdefault(stretch.status.value, [0, 0.0])
        entry[0] += 1
        entry[1] += stretch.length_m
    return {
        'near_poles': result.near_poles,
        'min_distance': digest_json({
            str(i): round(d, 6) for i, d in sorted(result.min_distance.items())
        }),
        'total_m': result.total_m,
        'unique_m': result.unique_m,
        'no_pole_m': result.no_pole_m,
        'backside_per_m': result.backside_per_m,
        'cables': [
            {
                'folder': cable.folder,
                'name': cable.name,
                'type': cable.cable_type,
                'length_m': cable.length_m,
                'unique_length_m': cable.unique_length_m,
                'no_pole_m': cable.no_pole_m,
                'near': digest_json({
                    str(i): round(d, 6) for i, d in sorted(cable.near.items())
                }),
            }
            for cable in cables
        ],
        'stretches': {
            'count': len(result.stretches),
            'by_status': by_status,
            'points': digest_json([
                [
                    s.cable,
                    s.status.value,
                    s.length_m,
                    describe_lines([s.points]),
                ]
                for s in result.stretches
            ]),
        },
    }
