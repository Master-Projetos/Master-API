import io
import zipfile
from collections import defaultdict
from xml.sax.saxutils import escape

from .engine import (
    DUPLICATE_M,
    NO_POLE_M,
    PARALLEL_M,
    Stretch,
    StretchStatus,
)

KML_HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
)
KML_FOOTER = '</Document></kml>'
POINT_ICON = 'http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png'

# (folder, KML color aabbggrr, [(lon, lat, description), ...])
PointGroup = tuple[str, str, list[tuple[float, float, str]]]


def _zip(kml: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as kmz:
        kmz.writestr('doc.kml', kml)
    return buffer.getvalue()


def _thousands(meters: float) -> str:
    return f'{meters:,.0f}'.replace(',', '.')


def points_kmz(title: str, groups: list[PointGroup]) -> bytes:
    parts = [KML_HEADER, f'<name>{escape(title)}</name>']
    for k, (_, color, _) in enumerate(groups):
        parts.append(
            f'<Style id="s{k}"><IconStyle><color>{color}</color>'
            f'<scale>0.5</scale><Icon><href>{POINT_ICON}</href></Icon>'
            '</IconStyle><LabelStyle><scale>0</scale></LabelStyle></Style>'
        )
    for k, (folder, _, points) in enumerate(groups):
        parts.append(f'<Folder><name>{escape(folder)} ({len(points)})</name>')
        parts.extend(
            f'<Placemark><description>{escape(description)}</description>'
            f'<styleUrl>#s{k}</styleUrl><Point><coordinates>'
            f'{lon:.7f},{lat:.7f},0</coordinates></Point></Placemark>'
            for lon, lat, description in points
        )
        parts.append('</Folder>')
    parts.append(KML_FOOTER)
    return _zip(''.join(parts))


def overlap_kmz(title: str, stretches: list[Stretch]) -> bytes:
    """What counts in the length, what has no pole and what is overlap."""
    total = defaultdict(float)
    for stretch in stretches:
        total[stretch.status] += stretch.length_m
    unique = total[StretchStatus.COUNTED] + total[StretchStatus.NO_POLE]
    # status, folder, KML color (aabbggrr), width
    groups = [
        (
            StretchStatus.OVERLAP,
            'Descontado: sobreposto a outro cabo '
            f'({_thousands(total[StretchStatus.OVERLAP])} m)',
            'ff0000ff',
            7,
        ),
        (
            StretchStatus.COUNTED,
            'Contado: sem sobreposição '
            f'({_thousands(total[StretchStatus.COUNTED])} m)',
            'ff00c000',
            3,
        ),
        (
            StretchStatus.NO_POLE,
            f'Contado, mas sem poste a menos de {NO_POLE_M:g} m '
            f'({_thousands(total[StretchStatus.NO_POLE])} m)',
            'ff00ffff',
            3,
        ),
    ]
    parts = [
        KML_HEADER,
        f'<name>{escape(title)}</name>',
        '<description>Total dos cabos: '
        f'{_thousands(unique + total[StretchStatus.OVERLAP])} m. '
        f'Sem sobreposição: {_thousands(unique)} m. Um trecho é descontado '
        f'quando passa a até {DUPLICATE_M:g} m de um cabo que vem antes no '
        f'KMZ de rotas, ou corre paralelo a ele a até {PARALLEL_M:g} m preso '
        'ao mesmo poste.</description>',
    ]
    for status, _, color, width in groups:
        parts.append(
            f'<Style id="{status}"><LineStyle><color>{color}</color>'
            f'<width>{width}</width></LineStyle></Style>'
        )
    for status, folder, _, _ in groups:
        parts.append(f'<Folder><name>{escape(folder)}</name>')
        for stretch in stretches:
            if stretch.status != status:
                continue
            coordinates = ' '.join(
                f'{lon:.7f},{lat:.7f},0' for lon, lat in stretch.points
            )
            parts.append(
                f'<Placemark><name>{escape(stretch.cable)}</name>'
                f'<description>{stretch.length_m:.1f} m</description>'
                f'<styleUrl>#{status}</styleUrl><LineString>'
                f'<tessellate>1</tessellate><coordinates>{coordinates}'
                '</coordinates></LineString></Placemark>'
            )
        parts.append('</Folder>')
    parts.append(KML_FOOTER)
    return _zip(''.join(parts))
