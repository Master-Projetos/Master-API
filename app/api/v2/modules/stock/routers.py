import logging

from fastapi import APIRouter, HTTPException, Request, Security

from app.core.limiter import limiter
from app.core.security import require_scope
from app.modules.api_key.model import Scope
from app.modules.stock.services import load_restock_schedule

from .schemas import RestockSchedule

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix='/stock',
    tags=['Stock'],
    dependencies=[Security(require_scope(Scope.STOCK_READ))],
)


@router.get('/restock-schedule', response_model=RestockSchedule)
@limiter.limit('30/minute')
def read_restock_schedule(request: Request):
    try:
        return load_restock_schedule()
    except Exception:
        logger.exception('failed to load the restock schedule')
        raise HTTPException(
            status_code=502, detail='Could not load the restock schedule'
        )
