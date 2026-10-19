from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Query, Request

from app.core.limiter import limiter
from app.core.security import SessionDep
from app.modules.route_poles.analysis.kmz import KmzKind
from app.modules.route_poles.analysis.pipeline import run_backbone
from app.modules.route_poles.backbone_service import (
    delete_backbone,
    get_backbone,
    list_backbones,
    load_city_kmz,
    save_backbone,
)
from app.modules.route_poles.schemas import BackboneSearch

from .backbone_schemas import BackboneDetail, BackbonePublic
from .dependencies import (
    BackboneOptionsDep,
    UploadDep,
    analyze_upload,
    read_scope,
    save_conflicts,
    write_scope,
)
from .presenters import backbone_public, kmz_response

router = APIRouter(prefix='/backbones')

BackboneRef = Annotated[
    str,
    Path(
        max_length=255,
        description='Backbone id (UUID) or code, e.g. 2026-10-19_backbone_bh',
    ),
]


@router.post(
    '',
    response_model=BackbonePublic,
    status_code=HTTPStatus.CREATED,
    dependencies=[write_scope],
)
@limiter.limit('5/minute')
async def upload_backbone(
    request: Request,
    session: SessionDep,
    upload: UploadDep,
    options: BackboneOptionsDep,
):
    """Analyses the backbone city by city, with the cables cut at each
    border, and stores it. Sending the same file on the same day replaces it.
    """
    data = await analyze_upload(run_backbone, upload, options)
    async with save_conflicts(session, 'Backbone'):
        row = await save_backbone(session, data)
    return backbone_public(request, row)


@router.get(
    '',
    response_model=list[BackbonePublic],
    dependencies=[read_scope],
)
@limiter.limit('60/minute')
async def read_backbones(
    request: Request,
    session: SessionDep,
    search: Annotated[BackboneSearch, Query()],
):
    return [
        backbone_public(request, row)
        for row in await list_backbones(session, search)
    ]


@router.get(
    '/{backbone_ref}',
    response_model=BackboneDetail,
    dependencies=[read_scope],
)
@limiter.limit('60/minute')
async def read_backbone(
    request: Request, session: SessionDep, backbone_ref: BackboneRef
):
    row = await get_backbone(session, backbone_ref, with_rows=True)
    if row is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Backbone not found'
        )
    return backbone_public(request, row, detail=True)


@router.delete(
    '/{backbone_ref}',
    status_code=HTTPStatus.NO_CONTENT,
    dependencies=[write_scope],
)
@limiter.limit('30/minute')
async def remove_backbone(
    request: Request, session: SessionDep, backbone_ref: BackboneRef
):
    if not await delete_backbone(session, backbone_ref):
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Backbone not found'
        )


# No API key, like the analyses KMZ: the random city id (UUID4) keeps the
# link private
@router.get('/cities/{city_id}/{kind}.kmz')
@limiter.limit('30/minute')
async def download_backbone_kmz(
    request: Request, city_id: UUID, kind: KmzKind, session: SessionDep
):
    return kmz_response(await load_city_kmz(session, city_id, kind), kind)
