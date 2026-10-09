import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Security

from app.core.constants import SWAP_SECTIONS
from app.core.limiter import limiter
from app.core.security import require_scope
from app.modules.api_key.model import Scope
from app.modules.swap.common import get_dashboard
from app.modules.swap.service import load_sections

from .schemas import SwapDashboard

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix='/swap',
    tags=['Swap'],
    dependencies=[Security(require_scope(Scope.SWAP_READ))],
)


@router.get('', response_model=SwapDashboard)
@limiter.limit('30/minute')
def read_swaps(
    request: Request,
    section: Annotated[
        list[str] | None,
        Query(description=f'One or more of {SWAP_SECTIONS}. Default: all'),
    ] = None,
):
    sections = list(dict.fromkeys(section)) if section else SWAP_SECTIONS

    unknown = set(sections) - set(SWAP_SECTIONS)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f'Unknown sections {sorted(unknown)}, use {SWAP_SECTIONS}',
        )

    try:
        df = load_sections(sections)
    except Exception:
        logger.exception('failed to load the swap spreadsheet')
        raise HTTPException(
            status_code=502, detail='Could not load the swap spreadsheet'
        )

    return get_dashboard(df)
