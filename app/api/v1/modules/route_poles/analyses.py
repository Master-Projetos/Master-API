from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Request, Response

from app.core.limiter import limiter
from app.core.security import SessionDep
from app.modules.route_poles.analysis.kmz import KmzKind
from app.modules.route_poles.analysis.pipeline import run_analysis
from app.modules.route_poles.analysis_service import (
    delete_analysis,
    get_analysis,
    list_analyses,
    load_kmz,
    save_analysis,
)
from app.modules.route_poles.csv_export import CsvTable, export_csv

from .dependencies import (
    AnalysisOptionsDep,
    UploadDep,
    analyze_upload,
    read_scope,
    save_conflicts,
    write_scope,
)
from .presenters import (
    analysis_kmz_url,
    analysis_public,
    kmz_links,
    kmz_response,
)
from .schemas import (
    RouteAnalysisCreated,
    RouteAnalysisDetail,
    RouteAnalysisPublic,
)

router = APIRouter()

CSV_MEDIA_TYPE = 'text/csv; charset=utf-8'

AnalysisRef = Annotated[
    str,
    Path(
        max_length=255,
        description='Analysis id (UUID) or the "ID análise" column, '
        'e.g. 2026-10-14_3122306_divinopolis',
    ),
]


@router.post(
    '/analyses',
    response_model=RouteAnalysisCreated,
    status_code=HTTPStatus.CREATED,
    dependencies=[write_scope],
)
@limiter.limit('5/minute')
async def upload_analysis(
    request: Request,
    session: SessionDep,
    upload: UploadDep,
    options: AnalysisOptionsDep,
):
    data = await analyze_upload(run_analysis, upload, options)
    async with save_conflicts(session, 'Analysis'):
        analysis = await save_analysis(session, data)

    # Both lengths go with the with/without overlap KMZ
    lengths = (
        {
            'length_with_overlap_m': data.length_with_overlap_m,
            'length_without_overlap_m': data.route_length_m,
        }
        if data.with_overlap_kmz is not None
        else {}
    )
    return RouteAnalysisCreated(
        id=analysis.id,
        code=analysis.code,
        **lengths,
        **kmz_links(
            request, 'download_kmz', data.kmz_kinds, analysis_id=analysis.id
        ),
    )


@router.get(
    '/analyses',
    response_model=list[RouteAnalysisPublic],
    dependencies=[read_scope],
)
@limiter.limit('60/minute')
async def read_analyses(
    request: Request, session: SessionDep, ibge_code: str | None = None
):
    return [
        analysis_public(request, row)
        for row in await list_analyses(session, ibge_code)
    ]


@router.get(
    '/analyses/{analysis_ref}',
    response_model=RouteAnalysisDetail,
    dependencies=[read_scope],
)
@limiter.limit('60/minute')
async def read_analysis(
    request: Request, session: SessionDep, analysis_ref: AnalysisRef
):
    row = await get_analysis(session, analysis_ref, with_rows=True)
    if row is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Analysis not found'
        )
    return analysis_public(request, row, detail=True)


@router.delete(
    '/analyses/{analysis_ref}',
    status_code=HTTPStatus.NO_CONTENT,
    dependencies=[write_scope],
)
@limiter.limit('30/minute')
async def remove_analysis(
    request: Request, session: SessionDep, analysis_ref: AnalysisRef
):
    if not await delete_analysis(session, analysis_ref):
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Analysis not found'
        )


@router.get('/csv/{table}.csv', dependencies=[read_scope])
@limiter.limit('60/minute')
async def read_csv(
    request: Request,
    session: SessionDep,
    table: CsvTable,
    ibge_code: str | None = None,
):
    content = await export_csv(
        session,
        table,
        ibge_code,
        lambda analysis_id, kind: analysis_kmz_url(request, analysis_id, kind),
    )
    return Response(content, media_type=CSV_MEDIA_TYPE)


# No API key: the links go into the spreadsheet cells, and the random id
# (UUID4) is what keeps them private
@router.get('/analyses/{analysis_id}/{kind}.kmz')
@limiter.limit('30/minute')
async def download_kmz(
    request: Request, analysis_id: UUID, kind: KmzKind, session: SessionDep
):
    return kmz_response(await load_kmz(session, analysis_id, kind), kind)
