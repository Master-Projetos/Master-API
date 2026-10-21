import logging

import pandas as pd

from app.core.constants import (
    MINIMAL_STOCK_DELETE,
    STOCK_V6_DELETE_COLUMNS,
    STOCK_V6_SHEET_URL,
    STOCK_V6_SHEETS,
)
from app.core.settings import get_settings
from app.modules.stock.services import (
    _to_records,
    load_stock_data,
    parse_ptbr_integers,
)

logger = logging.getLogger(__name__)

CONFIG_COLUMNS = ['code', 'description', 'unit', 'min_stock', 'safe_stock']


def _load_sheet(gid: str) -> list[dict]:
    sheet_df = pd.read_csv(
        f'{STOCK_V6_SHEET_URL}&gid={gid}',
        header=1,
        dtype={'Codmat': 'string'},
    )
    sheet_df['Saldo em Estoque'] = parse_ptbr_integers(
        sheet_df['Saldo em Estoque'].astype('string')
    ).fillna(0)
    sheet_df['code'] = sheet_df['Codmat'].str.strip()
    sheet_df = sheet_df.drop(columns=STOCK_V6_DELETE_COLUMNS, errors='ignore')

    grouped_df = sheet_df.groupby('code', as_index=False).agg(
        Descrição=('Descrição', 'first'),
        Unid=('Unid', 'first'),
        Saldo_em_Estoque=('Saldo em Estoque', 'sum'),
    )

    return (
        grouped_df
        .astype(object)
        .where(grouped_df.notna(), None)
        .to_dict(orient='records')
    )


def load_sheets(names: list[str]) -> dict[str, list[dict]]:
    logger.info('Fetching stock v6 tabs %s', names)

    return {name: _load_sheet(STOCK_V6_SHEETS[name]) for name in names}


def load_config() -> list[dict]:
    stock_df = load_stock_data()
    items_df = stock_df[CONFIG_COLUMNS].drop_duplicates(subset='code')

    return _to_records(items_df.reset_index(drop=True))


def get_minimal_stock() -> pd.DataFrame:
    minimal_stock_df = pd.read_csv(
        get_settings().STOCK_SHEET_URL, header=3, dtype='string'
    )
    minimal_stock_df = minimal_stock_df.drop(
        columns=MINIMAL_STOCK_DELETE, errors='ignore'
    )

    # the replenishment calendar below the items has its own endpoint
    minimal_stock_df['code'] = minimal_stock_df['Codmat'].str.strip()
    minimal_stock_df = minimal_stock_df.loc[
        : minimal_stock_df['code'].isna().idxmax() - 1
    ]
    minimal_stock_df['ESTOQUE MÍNIMO'] = pd.to_numeric(
        minimal_stock_df['ESTOQUE MÍNIMO'], errors='coerce'
    )

    return minimal_stock_df[['code', 'ESTOQUE MÍNIMO']].drop_duplicates(
        subset='code'
    )


def merge_minimal_stock(sheet_name: str) -> pd.DataFrame:
    stock_df = pd.DataFrame(_load_sheet(STOCK_V6_SHEETS[sheet_name]))

    # refurbished items (B + code) share the minimum of the original code
    stock_df['minimal_code'] = stock_df['code'].str.replace(
        r'^B(?=\d)', '', regex=True
    )
    merged_df = stock_df.merge(
        get_minimal_stock().rename(columns={'code': 'minimal_code'}),
        on='minimal_code',
        how='left',
    ).drop(columns='minimal_code')
    merged_df['ESTOQUE MÍNIMO'] = (
        merged_df['ESTOQUE MÍNIMO'].fillna(0).astype(int)
    )

    return merged_df
