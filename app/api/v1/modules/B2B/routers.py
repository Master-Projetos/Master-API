import logging

from fastapi import APIRouter, HTTPException, Request, Security

from app.core.limiter import limiter
from app.core.security import require_scope
from app.modules.api_key.model import Scope
from app.modules.b2b.services import get_dashboard, load_b2b_data

from .schemas import B2BDashboard

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix='/b2b',
    tags=['B2B'],
    dependencies=[Security(require_scope(Scope.B2B_READ))],
)


@router.get('/dashboard', response_model=B2BDashboard)
@limiter.limit('30/minute')
def read_dashboard(request: Request):
    try:
        df = load_b2b_data()
    except Exception:
        logger.exception('failed to load the B2B spreadsheet')
        raise HTTPException(
            status_code=502, detail='Could not load the B2B spreadsheet'
        )

    return get_dashboard(df)
