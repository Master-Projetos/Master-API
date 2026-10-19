from http import HTTPStatus
from urllib.parse import quote
from uuid import UUID

from fastapi import HTTPException, Request, Response
from pydantic import BaseModel

from app.modules.route_poles.analysis.kmz import KmzKind
from app.modules.route_poles.analysis_service import AnalysisRow
from app.modules.route_poles.backbone_service import BackboneRow
from app.modules.route_poles.model import StoredKmz

from .backbone_schemas import (
    BackboneCityDetail,
    BackboneCityPublic,
    BackboneDetail,
    BackbonePublic,
)
from .schemas import RouteAnalysisDetail, RouteAnalysisPublic

KMZ_MEDIA_TYPE = 'application/vnd.google-earth.kmz'
KMZ_FILE_PREFIX = {
    KmzKind.POLES: 'postes_utilizados',
    KmzKind.ALL_POLES: 'postes_municipio',
    KmzKind.OVERLAP: 'sobreposicao',
    KmzKind.WITH_OVERLAP: 'cabos_com_sobreposicao',
    KmzKind.WITHOUT_OVERLAP: 'cabos_sem_sobreposicao',
}


def public_url(request: Request, name: str, **params) -> str:
    url = request.url_for(name, **params)
    # Behind the cloud proxy the app sees http; keep the client's scheme
    scheme = request.headers.get('x-forwarded-proto', url.scheme)
    return str(url.replace(scheme=scheme))


def kmz_links(
    request: Request, route: str, kinds: frozenset[KmzKind], **params
) -> dict[str, str | None]:
    """<kind>_kmz_url for every KmzKind (None when the file doesn't exist)."""
    return {
        f'{kind.attr}_url': (
            public_url(request, route, kind=kind.value, **params)
            if kind in kinds
            else None
        )
        for kind in KmzKind
    }


def analysis_kmz_url(request: Request, analysis_id: UUID, kind: KmzKind):
    return public_url(
        request, 'download_kmz', analysis_id=analysis_id, kind=kind.value
    )


def build[T: BaseModel](schema: type[T], source, **extra) -> T:
    """The schema with its fields read from the source, plus the extra."""
    fields = {
        name: getattr(source, name)
        for name in schema.model_fields
        if name not in extra
    }
    return schema(**fields, **extra)


def analysis_public(
    request: Request, row: AnalysisRow, detail: bool = False
) -> RouteAnalysisPublic:
    analysis, kinds = row
    links = kmz_links(request, 'download_kmz', kinds, analysis_id=analysis.id)
    schema = RouteAnalysisDetail if detail else RouteAnalysisPublic
    return build(schema, analysis, **links)


def backbone_public(
    request: Request, row: BackboneRow, detail: bool = False
) -> BackbonePublic:
    backbone = row.backbone
    city_schema = BackboneCityDetail if detail else BackboneCityPublic
    cities = [
        build(
            city_schema,
            city,
            **kmz_links(
                request,
                'download_backbone_kmz',
                row.kmz_kinds[city.id],
                city_id=city.id,
            ),
        )
        for city in backbone.cities
    ]
    schema = BackboneDetail if detail else BackbonePublic
    return build(
        schema,
        backbone,
        cities=cities,
        cities_count=len(cities),
        route_length_m=sum(city.route_length_m for city in cities),
        near_poles=sum(city.near_poles for city in cities),
    )


def kmz_response(kmz: StoredKmz | None, kind: KmzKind) -> Response:
    if kmz is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='KMZ not found'
        )
    filename = quote(f'{KMZ_FILE_PREFIX[kind]}_{kmz.name}.kmz')
    return Response(
        kmz.content,
        media_type=KMZ_MEDIA_TYPE,
        headers={
            'Content-Disposition': f"attachment; filename*=UTF-8''{filename}"
        },
    )
