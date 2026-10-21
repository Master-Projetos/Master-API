import logging
from collections.abc import Callable
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import PurePath
from typing import Annotated

from fastapi import Depends, File, Form, HTTPException, Security, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_scope
from app.modules.api_key.model import Scope
from app.modules.route_poles.analysis.errors import AnalysisError, SourceError
from app.modules.route_poles.constants import (
    DEFAULT_RADIUS_M,
    MAX_UPLOAD_BYTES,
)
from app.modules.route_poles.schemas import AnalysisOptions, RouteUploadOptions

logger = logging.getLogger(__name__)

# The CSVs are read by Google Sheets IMPORTDATA, which can only pass the key
# in the URL (?key=...)
read_scope = Security(require_scope(Scope.ROUTE_POLES_READ, allow_query=True))
write_scope = Security(require_scope(Scope.ROUTE_POLES_WRITE))


@dataclass(frozen=True)
class Upload:
    content: bytes
    filename: str


async def read_file(file: UploadFile, default_name: str) -> Upload:
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            detail=f'File larger than {MAX_UPLOAD_BYTES // 1_000_000} MB',
        )
    return Upload(content, PurePath(file.filename or default_name).name)


async def read_upload(
    file: Annotated[UploadFile, File(description='Routes KMZ or KML')],
) -> Upload:
    return await read_file(file, 'routes.kmz')


async def read_licensed(
    licensed: Annotated[
        UploadFile,
        File(description='KMZ or KML with a marker for each licensed pole'),
    ],
) -> Upload:
    return await read_file(licensed, 'licensed.kmz')


async def read_routes(
    routes: Annotated[UploadFile, File(description='Routes KMZ or KML')],
) -> Upload:
    return await read_file(routes, 'routes.kmz')


UploadDep = Annotated[Upload, Depends(read_upload)]
LicensedDep = Annotated[Upload, Depends(read_licensed)]
RoutesDep = Annotated[Upload, Depends(read_routes)]


def form_options(
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
) -> dict:
    return {
        'radius_m': radius_m,
        'export_all': export_all,
        'overlap_kmz': overlap_kmz,
        'overlap_split_kmz': overlap_split_kmz,
    }


FormOptions = Annotated[dict, Depends(form_options)]


def validated[T: BaseModel](model: type[T], **fields) -> T:
    # A form model can't share the multipart body with a separate File field
    try:
        return model(**fields)
    except ValidationError as error:
        raise RequestValidationError(
            error.errors(include_url=False, include_context=False)
        ) from None


def analysis_options(
    common: FormOptions,
    city: Annotated[
        str | None, Form(description='Leave empty to detect from the routes')
    ] = None,
    ibge_code: Annotated[
        str | None, Form(description='7 digits, e.g. 3122306. Optional')
    ] = None,
) -> RouteUploadOptions:
    return validated(
        RouteUploadOptions, **common, city=city, ibge_code=ibge_code
    )


def backbone_options(common: FormOptions) -> AnalysisOptions:
    return validated(AnalysisOptions, **common)


AnalysisOptionsDep = Annotated[RouteUploadOptions, Depends(analysis_options)]
BackboneOptionsDep = Annotated[AnalysisOptions, Depends(backbone_options)]


@contextmanager
def upload_errors():
    """The analysis errors as the HTTP errors of an upload."""
    try:
        yield
    except SourceError as error:
        # IBGE/geodata-br down: not the client's fault, so not a 422
        logger.warning('city boundary unavailable: %s', error)
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY, detail=str(error)
        ) from None
    except AnalysisError as error:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY, detail=str(error)
        ) from None
    except ValidationError as error:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            # No input: it would echo the whole KMZ back
            detail=error.errors(
                include_url=False, include_context=False, include_input=False
            ),
        ) from None
    except OSError:
        logger.exception('failed to download the pole base or city boundary')
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY,
            detail='Could not download the pole base or the city boundary',
        ) from None


async def analyze_upload[T, O](
    job: Callable[[bytes, str, O], T], upload: Upload, options: O
) -> T:
    """Runs the job off the event loop: it is CPU-bound and downloads the
    pole bases and city boundaries.
    """
    with upload_errors():
        return await run_in_threadpool(
            job, upload.content, upload.filename, options
        )


@asynccontextmanager
async def save_conflicts(session: AsyncSession, what: str):
    try:
        yield
    except IntegrityError:
        # Two uploads of the same code at the same time
        await session.rollback()
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail=f'{what} is being saved by another request',
        ) from None
