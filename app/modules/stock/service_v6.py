import logging

import pandas as pd

from app.core.constants import (
    STOCK_V6_DELETE_COLUMNS,
    STOCK_V6_SHEET_URL,
    STOCK_V6_SHEETS,
)

from app.modules.stock.services import _to_records, load_stock_data

logger = logging.getLogger(__name__)

CONFIG_COLUMNS = ['code', 'description', 'unit', 'min_stock', 'safe_stock']


def _load_sheet(gid: str) -> list[dict]:
    """Download one tab, drop the unused columns and return its rows."""
    # The sheet is already treated, and its header is on the second row
    df = pd.read_csv(f'{STOCK_V6_SHEET_URL}&gid={gid}', header=1)
    df["Saldo em Estoque"] = pd.to_numeric(df["Saldo em Estoque"], errors="coerce").fillna(0)
    df = df.drop(columns=STOCK_V6_DELETE_COLUMNS, errors='ignore')
    group_df = df.groupby("Descrição", as_index=False).agg(
        Unid = ("Unid", "first"),
        Saldo_em_Estoque = ("Saldo em Estoque", "sum")
    )
    # Missing values become None instead of NaN, which is not valid JSON
    return group_df.astype(object).where(group_df.notna(), None).to_dict(orient='records')


def load_sheets(names: list[str]) -> dict[str, list[dict]]:
    """Rows of each requested tab."""
    logger.info('Fetching stock v6 tabs %s', names)

    return {name: _load_sheet(STOCK_V6_SHEETS[name]) for name in names}


def load_config() -> list[dict]:
    """Minimum and safe stock of each item, reusing the v2 stock sheet.

    Both are the same on every site, so the per-site rows are collapsed
    into one row per item.
    """
    df = load_stock_data()
    items = df[CONFIG_COLUMNS].drop_duplicates(subset='code')

    return _to_records(items.reset_index(drop=True))
