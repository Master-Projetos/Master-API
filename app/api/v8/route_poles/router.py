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
from app.modules.route_poles.constants import (
    DEFAULT_RADIUS_M,
    MAX_UPLOAD_BYTES,
)
from app.modules.route_poles.model import KmzKind, RouteCable, RouteCableType
from app.modules.route_poles.service_v8 import (
    AnalysisError,
    SourceError,
    cable_types_csv,
    cables_csv,
    delete_analysis,
    get_analysis,
    length_with_overlap,
    list_analyses,
    load_kmz,
    run_analysis,
    run_city_split_analysis,
    run_multi_city_analysis,
    save_analysis,
    save_city_analyses,
    summary_csv,
    update_analysis,
    update_row,
)

from .schemas import (
    BackboneCityAnalysis,
    BackboneCreated,
    CablePublic,
    CableTypePublic,
    CableTypeUpdate,
    CableUpdate,
    CityPublic,
    RouteAnalysisCreate,
    RouteAnalysisCreated,
    RouteAnalysisData,
    RouteAnalysisDetail,
    RouteAnalysisMultiCreated,
    RouteAnalysisPublic,
    RouteAnalysisUpdate,
    RouteUploadOptions,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/route-poles', tags=['Route poles'])

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
    """<kind>_kmz_url for every KmzKind (None when absent)."""
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
    radius_m: Annotated[float, Form()] = DEFAULT_RADIUS_M,
    export_all: Annotated[bool, Form()] = False,
    overlap_kmz: Annotated[bool, Form()] = False,
    overlap_split_kmz: Annotated[
        bool,
        Form(
            description='Also store the KMZ with and without overlap, and '
            'return both lengths'
        ),
    ] = False,
) -> RouteUploadOptions:
    # A form model can't share the multipart body with a separate File field
    try:
        return RouteUploadOptions(
            city=city,
            ibge_code=ibge_code,
            radius_m=radius_m,
            export_all=export_all,
            overlap_kmz=overlap_kmz,
            overlap_split_kmz=overlap_split_kmz,
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


def multi_upload_options(
    radius_m: Annotated[float, Form()] = DEFAULT_RADIUS_M,
    export_all: Annotated[bool, Form()] = False,
    overlap_kmz: Annotated[bool, Form()] = False,
    overlap_split_kmz: Annotated[
        bool,
        Form(
            description='Also store the KMZ with and without overlap, and '
            'return both lengths'
        ),
    ] = False,
) -> RouteUploadOptions:
    # The cities always come from the routes
    return upload_options(
        radius_m=radius_m,
        export_all=export_all,
        overlap_kmz=overlap_kmz,
        overlap_split_kmz=overlap_split_kmz,
    )


@router.post(
    '/analyses/upload-multi',
    response_model=RouteAnalysisMultiCreated,
    status_code=HTTPStatus.CREATED,
    dependencies=[write_scope],
)
@limiter.limit('5/minute')
async def upload_multi_city_analysis(
    request: Request,
    session: SessionDep,
    file: Annotated[UploadFile, File(description='Routes KMZ or KML')],
    options: Annotated[RouteUploadOptions, Depends(multi_upload_options)],
):
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            detail=f'File larger than {MAX_UPLOAD_BYTES // 1_000_000} MB',
        )
    filename = PurePath(file.filename or 'rotas.kmz').name

    try:
        data = await run_in_threadpool(
            run_multi_city_analysis, content, filename, options
        )
    except SourceError as error:
        logger.warning('city boundaries unavailable: %s', error)
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

    created = await store_analysis(request, session, data)
    return RouteAnalysisMultiCreated(
        **created.model_dump(), cities=data.cities
    )


@router.post(
    '/analyses/upload-backbone',
    response_model=BackboneCreated,
    status_code=HTTPStatus.CREATED,
    dependencies=[write_scope],
)
@limiter.limit('5/minute')
async def upload_backbone_analysis(
    request: Request,
    session: SessionDep,
    file: Annotated[UploadFile, File(description='Backbone KMZ or KML')],
    options: Annotated[RouteUploadOptions, Depends(multi_upload_options)],
):
    """One analysis per city the backbone passes through, with the cables
    cut at each border. A city that already has an analysis gets this one
    summed into its latest (average span and KMZ files kept); otherwise a
    new analysis is created.
    """
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            detail=f'File larger than {MAX_UPLOAD_BYTES // 1_000_000} MB',
        )
    filename = PurePath(file.filename or 'backbone.kmz').name

    try:
        analyses = await run_in_threadpool(
            run_city_split_analysis, content, filename, options
        )
    except SourceError as error:
        logger.warning('city boundaries unavailable: %s', error)
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

    try:
        saved = await save_city_analyses(session, analyses)
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail='Analysis is being saved by another request',
        )

    cities = []
    for analysis, merged in saved:
        # Reloaded with its rows and the KMZ files it has
        session.expunge(analysis)
        row = await get_analysis(session, str(analysis.id), with_rows=True)
        detail = public_analysis(request, *row, detail=True)
        cities.append(
            BackboneCityAnalysis(**detail.model_dump(), merged=merged)
        )
    return BackboneCreated(cities=cities)


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

    kinds = frozenset(
        kind
        for kind in KmzKind
        if getattr(data, kind.column.key) is not None
    )
    # Both lengths go with the with/without overlap KMZ
    lengths = (
        {
            'length_with_overlap_m': length_with_overlap(data.cable_types),
            'length_without_overlap_m': data.route_length_m,
        }
        if data.with_overlap_kmz is not None
        else {}
    )
    return RouteAnalysisCreated(
        id=analysis.id,
        code=analysis.code,
        **lengths,
        **kmz_links(request, analysis.id, kinds),
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
        if name not in links and name != 'cities'
    }
    if detail:
        fields['cities'] = [
            CityPublic.model_validate(row) for row in analysis.cities
        ]
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
    KmzKind.WITH_OVERLAP: 'cabos_com_sobreposicao',
    KmzKind.WITHOUT_OVERLAP: 'cabos_sem_sobreposicao',
}


# The KMZ route has no API key: the links go into the spreadsheet cells, and
# the random analysis id (UUID4) is what keeps them private.
# poles.kmz, all-poles.kmz, overlap.kmz, with-overlap.kmz or
# without-overlap.kmz
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
