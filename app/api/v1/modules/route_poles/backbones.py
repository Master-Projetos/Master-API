import asyncio
import logging
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Query, Request

from app.core.database import async_session
from app.core.limiter import limiter
from app.core.security import SessionDep
from app.modules.route_poles.analysis.kmz import KmzKind
from app.modules.route_poles.analysis.pipeline import run_backbone
from app.modules.route_poles.backbone_service import (
    BackboneRow,
    delete_backbone,
    get_backbone,
    list_backbones,
    load_city_kmz,
    save_backbone,
)
from app.modules.route_poles.jobs import BackboneJob, create_job, get_job
from app.modules.route_poles.schemas import AnalysisOptions, BackboneSearch

from .backbone_schemas import BackboneDetail, BackboneJobPublic, BackbonePublic
from .dependencies import (
    BackboneOptionsDep,
    Upload,
    UploadDep,
    analyze_upload,
    read_scope,
    save_conflicts,
    write_scope,
)
from .presenters import backbone_public, job_public, kmz_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/backbones')

background_tasks: set[asyncio.Task] = set()

BackboneRef = Annotated[
    str,
    Path(
        max_length=255,
        description='Backbone id (UUID) or code, e.g. 2026-10-19_backbone_bh',
    ),
]


async def analyze_and_save(
    job: BackboneJob, upload: Upload, options: AnalysisOptions
) -> BackboneRow:
    data = await analyze_upload(
        lambda content, filename, opts: run_backbone(
            content, filename, opts, job.progress
        ),
        upload,
        options,
    )
    job.stage = 'saving'
    async with async_session() as session:
        async with save_conflicts(session, 'Backbone'):
            return await save_backbone(session, data)


async def run_backbone_job(
    job: BackboneJob, upload: Upload, options: AnalysisOptions
) -> None:
    try:
        row = await analyze_and_save(job, upload, options)
        job.complete(row.backbone.id, row.backbone.code)
    except HTTPException as error:
        job.fail(str(error.detail))
    except Exception:
        logger.exception('backbone job %s failed', job.id)
        job.fail('Unexpected error while analysing the backbone')


def spawn_backbone_job(
    upload: Upload, options: AnalysisOptions, licensed_code: str | None = None
) -> BackboneJob:
    job = create_job(upload.filename)
    job.licensed_code = licensed_code
    task = asyncio.create_task(run_backbone_job(job, upload, options))
    # The loop only keeps weak references to tasks
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)
    return job


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


@router.post(
    '/jobs',
    response_model=BackboneJobPublic,
    status_code=HTTPStatus.ACCEPTED,
    dependencies=[write_scope],
)
@limiter.limit('5/minute')
async def start_backbone_job(
    request: Request, upload: UploadDep, options: BackboneOptionsDep
):
    """Same as the upload, but returns at once: follow the progress in the
    job and take the stored backbone from it when it completes.
    """
    return job_public(request, spawn_backbone_job(upload, options))


@router.get(
    '/jobs/{job_id}',
    response_model=BackboneJobPublic,
    dependencies=[read_scope],
)
@limiter.limit('120/minute')
async def read_backbone_job(request: Request, job_id: UUID):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Job not found'
        )
    return job_public(request, job)


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
