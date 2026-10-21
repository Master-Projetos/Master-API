from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.limiter import limiter
from app.core.security import SessionDep
from app.modules.route_poles.analysis.licensing import comparison_kmz
from app.modules.route_poles.analysis.pipeline import run_licensed
from app.modules.route_poles.licensed_service import (
    compare_licensed,
    delete_licensed,
    get_licensed,
    list_licensed,
    save_licensed,
)

from .backbone_schemas import BackboneJobPublic
from .backbones import spawn_backbone_job
from .dependencies import (
    BackboneOptionsDep,
    LicensedDep,
    RoutesDep,
    Upload,
    analyze_upload,
    read_scope,
    save_conflicts,
    write_scope,
)
from .licensed_schemas import LicensedSetDetail, LicensedSetSummary
from .presenters import (
    job_public,
    kmz_download,
    licensed_detail,
    licensed_summary,
)

router = APIRouter(prefix='/licensed-poles')

LicensedRef = Annotated[
    str,
    Path(
        max_length=255,
        description='Licensed poles id (UUID) or code, '
        'e.g. 2026-10-20_licensed_bh',
    ),
]


async def store_licensed(session: AsyncSession, upload: Upload) -> str:
    """Finds the cities of the markers and stores them; returns the code."""
    data = await analyze_upload(run_licensed, upload, None)
    async with save_conflicts(session, 'Licensed poles'):
        await save_licensed(session, data)
    return data.code


async def read_licensed_or_404(session: AsyncSession, ref: str):
    licensed = await get_licensed(session, ref, with_markers=True)
    if licensed is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Licensed poles not found'
        )
    return licensed


@router.post(
    '',
    response_model=LicensedSetDetail,
    status_code=HTTPStatus.CREATED,
    dependencies=[write_scope],
)
@limiter.limit('5/minute')
async def upload_licensed(
    request: Request, session: SessionDep, licensed: LicensedDep
):
    """Stores the licensed poles and compares each city with the latest
    analysis of it. A city with no analysis yet is pending: it is compared
    as soon as a backbone or an analysis of it is stored.
    """
    code = await store_licensed(session, licensed)
    stored = await read_licensed_or_404(session, code)
    result = await compare_licensed(session, stored)
    return licensed_detail(request, stored, result)


@router.post(
    '/jobs',
    response_model=BackboneJobPublic,
    status_code=HTTPStatus.ACCEPTED,
    dependencies=[write_scope],
)
@limiter.limit('5/minute')
async def start_licensed_job(
    request: Request,
    session: SessionDep,
    licensed: LicensedDep,
    routes: RoutesDep,
    options: BackboneOptionsDep,
):
    """Stores the licensed poles and starts the backbone job of the routes.
    When the job completes, read the comparison in licensed_url.
    """
    code = await store_licensed(session, licensed)
    return job_public(request, spawn_backbone_job(routes, options, code))


@router.get(
    '',
    response_model=list[LicensedSetSummary],
    dependencies=[read_scope],
)
@limiter.limit('60/minute')
async def read_licensed_sets(
    request: Request,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return [
        licensed_summary(licensed)
        for licensed in await list_licensed(session, limit, offset)
    ]


@router.get(
    '/{licensed_ref}',
    response_model=LicensedSetDetail,
    dependencies=[read_scope],
)
@limiter.limit('30/minute')
async def read_licensed(
    request: Request, session: SessionDep, licensed_ref: LicensedRef
):
    licensed = await read_licensed_or_404(session, licensed_ref)
    result = await compare_licensed(session, licensed)
    return licensed_detail(request, licensed, result)


@router.get('/{licensed_ref}/comparison.kmz', dependencies=[read_scope])
@limiter.limit('30/minute')
async def download_licensed_kmz(
    request: Request, session: SessionDep, licensed_ref: LicensedRef
):
    licensed = await read_licensed_or_404(session, licensed_ref)
    result = await compare_licensed(session, licensed)
    compared = [city for city in result.cities if city.comparison]
    pending = [
        tuple(marker)
        for city in result.cities
        if city.comparison is None
        for marker in city.city.markers
    ]
    content = comparison_kmz(
        f'Licenciados x utilizados - {licensed.code}',
        [city.comparison for city in compared],
        pending,
        result.outside,
    )
    return kmz_download(f'licenciados_{licensed.code}', content)


@router.delete(
    '/{licensed_ref}',
    status_code=HTTPStatus.NO_CONTENT,
    dependencies=[write_scope],
)
@limiter.limit('30/minute')
async def remove_licensed(
    request: Request, session: SessionDep, licensed_ref: LicensedRef
):
    if not await delete_licensed(session, licensed_ref):
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Licensed poles not found'
        )
