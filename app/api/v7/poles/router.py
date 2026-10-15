import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Security

from app.core.limiter import limiter
from app.core.security import require_scope
from app.modules.api_key.model import Scope
from app.modules.poles.service_v7 import load_poles

from .schemas import UtilityPoles

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix='/poles',
    tags=['Poles'],
    dependencies=[Security(require_scope(Scope.POLES_READ))],
)


@router.get('', response_model=list[UtilityPoles])
@limiter.limit('10/minute')
def read_poles(
    request: Request,
    utility: Annotated[
        list[str] | None,
        Query(description='One or more utilities, e.g. CEMIG. Default: all'),
    ] = None,
):
    names = [u.strip().upper() for u in dict.fromkeys(utility)] if utility else None

    try:
        return load_poles(names)
    except LookupError as error:
        raise HTTPException(
            status_code=422, detail=f'Unknown utilities {error.args[0]}'
        )
    except Exception:
        logger.exception('failed to load the poles v7 spreadsheet')
        raise HTTPException(
            status_code=502, detail='Could not load the poles spreadsheet'
        )
