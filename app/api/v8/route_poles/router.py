import logging
from http import HTTPStatus
from pathlib import PurePath
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Path,
    Request,
    Response,
    Security,
    UploadFile,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.core.limiter import limiter
from app.core.security import SessionDep, require_scope
from app.modules.api_key.model import Scope
from app.modules.route_poles.model import KmzKind, RouteCable, RouteCableType
from app.modules.route_poles.service_v8 import (
    AnalysisError,
    SourceError,
    cable_types_csv,
    cables_csv,
    delete_analysis,
    get_analysis,
    list_analyses,
    load_kmz,
    run_analysis,
    save_analysis,
    summary_csv,
    update_analysis,
    update_row,
)

from .schemas import (
    CablePublic,
    CableTypePublic,
    CableTypeUpdate,
    CableUpdate,
    RouteAnalysisCreate,
    RouteAnalysisCreated,
    RouteAnalysisData,
    RouteAnalysisDetail,
    RouteAnalysisPublic,
    RouteAnalysisUpdate,
    RouteUploadOptions,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/route-poles', tags=['Route poles'])

MAX_UPLOAD_BYTES = 50_000_000

# The CSVs are read by Google Sheets IMPORTDATA, which can only pass the key
# in the URL (?key=...)
read_scope = Security(require_scope(Scope.ROUTE_POLES_READ, allow_query=True))
write_scope = Security(require_scope(Scope.ROUTE_POLES_WRITE))

CSV_MEDIA_TYPE = 'text/csv; charset=utf-8'

AnalysisRef = Annotated[
    str,
    Path(
        max_length=255,
        description='Analysis id (UUID) or the "ID análise" column, '
        'e.g. 2026-10-14_3122306_divinopolis',
    ),
]
KMZ_MEDIA_TYPE = 'application/vnd.google-earth.kmz'


def public_url(request: Request, name: str, **params) -> str:
    url = request.url_for(name, **params)
    # Behind the cloud proxy the app sees http; keep the client's scheme
    scheme = request.headers.get('x-forwarded-proto', url.scheme)
    return str(url.replace(scheme=scheme))


def kmz_url(request: Request, analysis_id: UUID, kind: KmzKind) -> str:
    return public_url(
        request, 'download_kmz', analysis_id=analysis_id, kind=kind.value
    )


def kmz_links(
    request: Request, analysis_id: UUID, kinds: frozenset[KmzKind]
) -> dict[str, str | None]:
    """poles_kmz_url, all_poles_kmz_url, overlap_kmz_url (None when absent)."""
    return {
        f'{kind.name.lower()}_kmz_url': (
            kmz_url(request, analysis_id, kind) if kind in kinds else None
        )
        for kind in KmzKind
    }


@router.post(
    '/analyses',
    response_model=RouteAnalysisCreated,
    status_code=HTTPStatus.CREATED,
    dependencies=[write_scope],
)
@limiter.limit('30/minute')
async def create_analysis(
    request: Request, data: RouteAnalysisCreate, session: SessionDep
):
    return await store_analysis(request, session, data)


def upload_options(
    city: Annotated[
        str | None, Form(description='Leave empty to detect from the routes')
    ] = None,
    ibge_code: Annotated[
        str | None, Form(description='7 digits, e.g. 3122306. Optional')
    ] = None,
    radius_m: Annotated[float, Form()] = 25.0,
    export_all: Annotated[bool, Form()] = False,
    overlap_kmz: Annotated[bool, Form()] = False,
) -> RouteUploadOptions:
    # A form model can't share the multipart body with a separate File field
    try:
        return RouteUploadOptions(
            city=city,
            ibge_code=ibge_code,
            radius_m=radius_m,
            export_all=export_all,
            overlap_kmz=overlap_kmz,
        )
    except ValidationError as error:
        raise RequestValidationError(
            error.errors(include_url=False, include_context=False)
        )


@router.post(
    '/analyses/upload',
    response_model=RouteAnalysisCreated,
    status_code=HTTPStatus.CREATED,
    dependencies=[write_scope],
)
@limiter.limit('5/minute')
async def upload_analysis(
    request: Request,
    session: SessionDep,
    file: Annotated[UploadFile, File(description='Routes KMZ or KML')],
    options: Annotated[RouteUploadOptions, Depends(upload_options)],
):
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            detail=f'File larger than {MAX_UPLOAD_BYTES // 1_000_000} MB',
        )
    filename = PurePath(file.filename or 'rotas.kmz').name

    try:
        # CPU-bound and downloads the pole base/city boundary: off the loop
        data = await run_in_threadpool(
            run_analysis, content, filename, options
        )
    except SourceError as error:
        # IBGE/geodata-br down: not the client's fault, so not a 422
        logger.warning('city boundary unavailable: %s', error)
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY, detail=str(error)
        )
    except AnalysisError as error:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY, detail=str(error)
        )
    except ValidationError as error:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            # No input: it would echo the whole base64 KMZ back
            detail=error.errors(
                include_url=False, include_context=False, include_input=False
            ),
        )
    except OSError:
        logger.exception('failed to download the pole base or city boundary')
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY,
            detail='Could not download the pole base or the city boundary',
        )

    return await store_analysis(request, session, data)


async def store_analysis(
    request: Request, session: SessionDep, data: RouteAnalysisData
) -> RouteAnalysisCreated:
    try:
        analysis = await save_analysis(session, data)
    except IntegrityError:
        # Two uploads of the same analysis at the same time
        await session.rollback()
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail='Analysis is being saved by another request',
        )

    kinds = {KmzKind.POLES}
    if data.all_poles_kmz:
        kinds.add(KmzKind.ALL_POLES)
    if data.overlap_kmz:
        kinds.add(KmzKind.OVERLAP)
    return RouteAnalysisCreated(
        id=analysis.id,
        code=analysis.code,
        **kmz_links(request, analysis.id, frozenset(kinds)),
    )


def public_analysis(
    request: Request,
    analysis,
    kmz_kinds: frozenset[KmzKind],
    detail: bool = False,
) -> RouteAnalysisPublic:
    links = kmz_links(request, analysis.id, kmz_kinds)
    schema = RouteAnalysisDetail if detail else RouteAnalysisPublic
    fields = {
        name: getattr(analysis, name)
        for name in schema.model_fields
        if name not in links
    }
    if detail:
        fields['cable_types'] = [
            CableTypePublic.model_validate(row) for row in analysis.cable_types
        ]
        fields['cables'] = [
            CablePublic.model_validate(row) for row in analysis.cables
        ]
    return schema(**fields, **links)


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
        public_analysis(request, analysis, kmz_kinds)
        for analysis, kmz_kinds in await list_analyses(session, ibge_code)
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
    return public_analysis(request, *row, detail=True)


@router.patch(
    '/analyses/{analysis_ref}',
    response_model=RouteAnalysisPublic,
    dependencies=[write_scope],
)
@limiter.limit('30/minute')
async def edit_analysis(
    request: Request,
    session: SessionDep,
    analysis_ref: AnalysisRef,
    changes: RouteAnalysisUpdate,
):
    row = await update_analysis(
        session, analysis_ref, changes.model_dump(exclude_unset=True)
    )
    if row is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Analysis not found'
        )
    return public_analysis(request, *row)


@router.patch(
    '/cable-types/{row_id}',
    response_model=CableTypePublic,
    dependencies=[write_scope],
)
@limiter.limit('30/minute')
async def edit_cable_type(
    request: Request,
    session: SessionDep,
    row_id: UUID,
    changes: CableTypeUpdate,
):
    row = await update_row(
        session, RouteCableType, row_id, changes.model_dump(exclude_unset=True)
    )
    if row is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Cable type not found'
        )
    return row


@router.patch(
    '/cables/{row_id}',
    response_model=CablePublic,
    dependencies=[write_scope],
)
@limiter.limit('30/minute')
async def edit_cable(
    request: Request,
    session: SessionDep,
    row_id: UUID,
    changes: CableUpdate,
):
    row = await update_row(
        session, RouteCable, row_id, changes.model_dump(exclude_unset=True)
    )
    if row is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Cable not found'
        )
    return row


@router.delete(
    '/analyses/{analysis_ref}',
    status_code=HTTPStatus.NO_CONTENT,
    dependencies=[write_scope],
)
@limiter.limit('30/minute')
async def remove_analysis(
    request: Request,
    session: SessionDep,
    analysis_ref: AnalysisRef,
):
    if not await delete_analysis(session, analysis_ref):
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Analysis not found'
        )


@router.get('/summary.csv', dependencies=[read_scope])
@limiter.limit('60/minute')
async def read_summary_csv(
    request: Request, session: SessionDep, ibge_code: str | None = None
):
    content = await summary_csv(
        session,
        ibge_code,
        lambda analysis_id, kind: kmz_url(request, analysis_id, kind),
    )
    return Response(content, media_type=CSV_MEDIA_TYPE)


@router.get('/cable-types.csv', dependencies=[read_scope])
@limiter.limit('60/minute')
async def read_cable_types_csv(
    request: Request, session: SessionDep, ibge_code: str | None = None
):
    content = await cable_types_csv(session, ibge_code)
    return Response(content, media_type=CSV_MEDIA_TYPE)


@router.get('/cables.csv', dependencies=[read_scope])
@limiter.limit('60/minute')
async def read_cables_csv(
    request: Request, session: SessionDep, ibge_code: str | None = None
):
    content = await cables_csv(session, ibge_code)
    return Response(content, media_type=CSV_MEDIA_TYPE)


KMZ_FILE_PREFIX = {
    KmzKind.POLES: 'postes_utilizados',
    KmzKind.ALL_POLES: 'postes_municipio',
    KmzKind.OVERLAP: 'sobreposicao',
}


# The KMZ route has no API key: the links go into the spreadsheet cells, and
# the random analysis id (UUID4) is what keeps them private.
# poles.kmz, all-poles.kmz or overlap.kmz
@router.get('/analyses/{analysis_id}/{kind}.kmz')
@limiter.limit('30/minute')
async def download_kmz(
    request: Request, analysis_id: UUID, kind: KmzKind, session: SessionDep
):
    kmz = await load_kmz(session, analysis_id, kind)
    if kmz is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='KMZ not found'
        )

    code, content = kmz
    filename = quote(f'{KMZ_FILE_PREFIX[kind]}_{code}.kmz')
    return Response(
        content,
        media_type=KMZ_MEDIA_TYPE,
        headers={
            'Content-Disposition': f"attachment; filename*=UTF-8''{filename}"
        },
    )
