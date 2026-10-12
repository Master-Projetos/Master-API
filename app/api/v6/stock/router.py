import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Security

from app.core.constants import STOCK_V6_SHEETS
from app.core.limiter import limiter
from app.core.security import require_scope
from app.modules.api_key.model import Scope
from app.modules.stock.service_v6 import load_config, load_sheets, merge_minimal_stock

from .schemas import StockConfigItem, StockSheets

logger = logging.getLogger(__name__)

SHEET_NAMES = list(STOCK_V6_SHEETS)

router = APIRouter(
    prefix='/stock',
    tags=['Stock'],
    dependencies=[Security(require_scope(Scope.STOCK_READ))],
)


@router.get('/config', response_model=list[StockConfigItem])
@limiter.limit('30/minute')
def read_config(request: Request):
    try:
        return load_config()
    except Exception:
        logger.exception('failed to load the stock config')
        raise HTTPException(
            status_code=502, detail='Could not load the stock spreadsheet'
        )


@router.get('', response_model=StockSheets)
@limiter.limit('30/minute')
def read_stock(
    request: Request,
    sheet: Annotated[
        list[str] | None,
        Query(description=f'One or more of {SHEET_NAMES}. Default: all'),
    ] = None,
):
    names = list(dict.fromkeys(sheet)) if sheet else SHEET_NAMES

    unknown = set(names) - set(SHEET_NAMES)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f'Unknown sheets {sorted(unknown)}, use {SHEET_NAMES}',
        )

    try:
        return {'sheets': load_sheets(names)}
    except Exception:
        logger.exception('failed to load the stock v6 spreadsheet')
        raise HTTPException(
            status_code=502, detail='Could not load the stock spreadsheet'
        )

@router.get('/minimal')
@limiter.limit('10/minute')
def get_stock_with_minimal(
        request: Request
):
    merge_sheet = {}

    for stock in SHEET_NAMES:
        merge_df = merge_minimal_stock(stock)
        merge_sheet[stock] = merge_df.astype(object).where(merge_df.notna(), None).to_dict(orient='records')

    return merge_sheet