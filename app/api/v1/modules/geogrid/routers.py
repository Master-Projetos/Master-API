import logging
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    HTTPException,
    Query,
    Request,
    Security,
)

from app.api.v1.modules.geogrid.schemas import (
    CriticalCtosResponse,
    ReportSchema,
    Viabily,
)
from app.core.constants import ALLOWED_RELATORIES
from app.core.limiter import limiter
from app.core.security import require_scope
from app.modules.api_key.model import Scope
lazy from app.modules.geogrid.critical_ctos import (
    SheetUnavailableError,
    find_critical_ctos,
)
lazy from app.modules.geogrid.service import (
    export_lock,
    get_status,
    run_export,
    treat_viabilidade,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=['Geogrid'],
    dependencies=[Security(require_scope(Scope.GEOGRID_READ))],
)


@router.get('/{relatory}/status')
@limiter.limit('200/minute')
def get_export_status(request: Request, relatory: str):
    status = get_status(relatory)

    if not status:
        logger.warning(
            'relatory=%s: status requested but no export found', relatory
        )
        raise HTTPException(
            status_code=404, detail='No export found for the relatory'
        )
    return status


@router.post('/{relatory}', response_model=ReportSchema)
@limiter.limit('2/minute')
def request_export(
    request: Request, relatory: str, background_tasks: BackgroundTasks
):
    if relatory not in ALLOWED_RELATORIES:
        logger.warning(
            'relatory=%s: export requested but not supported', relatory
        )
        raise HTTPException(status_code=400, detail='Relatory not supported')

    if export_lock.locked():
        logger.info(
            'relatory=%s: export requested but another export is '
            'already running',
            relatory,
        )
        raise HTTPException(
            status_code=409, detail='Another export is already running'
        )

    logger.info('relatory=%s: export enqueued', relatory)
    background_tasks.add_task(run_export, relatory)
    return {'status': 'processing', 'relatory': relatory}


@router.get('/viability', response_model=Viabily)
@limiter.limit('10/minute')
def get_data(request: Request):
    viability_json = treat_viabilidade()
    if viability_json is None:
        logger.warning('viability data requested but not found')
        raise HTTPException(status_code=400, detail='Relatory has not find')

    return viability_json


@router.get('/viability/critical-ctos', response_model=CriticalCtosResponse)
@limiter.limit('10/minute')
def get_critical_ctos(
    request: Request,
    max_livres: Annotated[
        int,
        Query(ge=0, description='Critical with at most this many free ports'),
    ] = 1,
):
    try:
        result = find_critical_ctos(max_livres)
    except SheetUnavailableError as error:
        logger.error('critical CTOs: attendants sheet unavailable: %s', error)
        raise HTTPException(
            status_code=502, detail='Attendants sheet unavailable'
        ) from error

    if result is None:
        logger.warning('critical CTOs requested but viability not found')
        raise HTTPException(status_code=400, detail='Relatory has not find')

    return result
