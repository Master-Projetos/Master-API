import logging
from io import BytesIO

import pandas as pd
import requests

from app.core.constants import SWAP_V5_SHEET_URL
from app.modules.swap.common import (
    CHECKED,
    DATE_COLUMNS,
    MISSING_INFO,
    UNCHECKED,
    UNTITLED_SECTION,
    clean_text,
    parse_date,
    parse_number,
    parse_text,
    split_untitled,
)

logger = logging.getLogger(__name__)

FETCH_TIMEOUT_SECONDS = 30

CONTRACTS_SHEET = 'contratos'

# The dark fiber tab also holds trunk and transport, split like v4's
# untitled table
SECTION_SHEETS = {
    'fibra_apagada': UNTITLED_SECTION,
    'lambda': 'lambdas',
    'colocation': 'colocation',
    'capacidade': 'capacity',
    'lan_to_lan': 'lan-to-lan',
    'last_mille': 'last_mille',
    'porta_switch': 'switch_port',
    'link_ip': 'link_ip',
}

# Not every tab has every column, e.g. colocation has no distances
ROW_COLUMNS = {
    'contrato_id': 'contract_id',
    'parceiro': 'partner',
    'cessao': 'assignment',
    'circuito': 'circuit',
    'acordo': 'agreement',
    'quantidade': 'quantity',
    'distancia_km': 'distance_km',
    'km_fibra': 'fiber_km',
    'status': 'status',
    'status_obs': 'status_notes',
    'conferencia': 'check',
}
# A renamed header would otherwise read as an empty column
REQUIRED_ROW_COLUMNS = {'parceiro', 'circuito', 'acordo', 'conferencia'}

# "contrato_link" is left out on purpose: contract documents are sensitive
CONTRACT_COLUMNS = {
    'contrato_id': 'contract_id',
    'contrato_obs': 'contract_status',
    'vigencia_anos': 'term_years',
    'vigencia_obs': 'term_notes',
    'data_celebracao': 'signed_at',
    'data_termino': 'ends_at',
}

TEXT_COLUMNS = (
    'partner',
    'contract_status',
    'term_notes',
    'assignment',
    'circuit',
    'agreement',
    'quantity',
    'status',
    'status_notes',
)
NUMERIC_COLUMNS = ('distance_km', 'fiber_km')

RESPONSE_COLUMNS = [
    'section',
    'contract_id',
    'partner',
    'contract_status',
    'term',
    'assignment',
    'circuit',
    'agreement',
    'quantity',
    'distance_km',
    'fiber_km',
    'status',
    'signed_at',
    'ends_at',
    'check_status',
]

CHECKS = {
    'CONCLUIDO': CHECKED,
    'PENDENTE': MISSING_INFO,
    'NAO CONFERIDO': UNCHECKED,
}


def _fetch_sheets() -> dict[str, pd.DataFrame]:
    logger.info('Fetching swap v5 spreadsheet')
    response = requests.get(SWAP_V5_SHEET_URL, timeout=FETCH_TIMEOUT_SECONDS)
    response.raise_for_status()

    sheets = pd.read_excel(
        BytesIO(response.content),
        sheet_name=[CONTRACTS_SHEET, *SECTION_SHEETS],
        engine='openpyxl',
    )

    return {
        name: df.dropna(how='all').map(clean_text)
        for name, df in sheets.items()
    }


def _section_rows(sheets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    frames = []
    for sheet, section in SECTION_SHEETS.items():
        df = sheets[sheet]

        missing = REQUIRED_ROW_COLUMNS - set(df.columns)
        if missing:
            raise ValueError(f'Swap tab "{sheet}" has no {sorted(missing)}')

        df = df.reindex(columns=list(ROW_COLUMNS)).rename(columns=ROW_COLUMNS)
        frames.append(df.assign(section=section))

    return pd.concat(frames, ignore_index=True)


def _contracts(sheet: pd.DataFrame) -> pd.DataFrame:
    df = sheet.reindex(columns=list(CONTRACT_COLUMNS)).rename(
        columns=CONTRACT_COLUMNS
    )
    df['contract_id'] = df['contract_id'].map(parse_number).astype('Int64')

    return df.dropna(subset=['contract_id'])


def _join_contracts(
    rows: pd.DataFrame, contracts: pd.DataFrame
) -> pd.DataFrame:
    rows['contract_id'] = rows['contract_id'].map(parse_number).astype('Int64')

    # Fails on a repeated contract id instead of duplicating its rows
    df = rows.merge(
        contracts, on='contract_id', how='left', validate='many_to_one'
    )

    orphans = set(rows['contract_id'].dropna()) - set(contracts['contract_id'])
    if orphans:
        logger.warning(
            'Swap rows point to unknown contracts %s', sorted(orphans)
        )

    return df


def _check_statuses(checks: pd.Series) -> pd.Series:
    checks = checks.str.upper()

    unknown = set(checks.dropna()) - set(CHECKS)
    if unknown:
        logger.warning(
            'Unknown swap check values %s, read as unchecked', sorted(unknown)
        )

    return checks.map(CHECKS).fillna(UNCHECKED)


def _term(years: object, notes: object) -> str | None:
    """Term the way v4 wrote it, like "15 ANOS (A contar da ...)"."""
    parts = []
    if pd.notna(years):
        parts.append(f'{int(years)} ANOS')
    if pd.notna(notes):
        parts.append(f'({notes})' if parts else str(notes))

    return ' '.join(parts) or None


def _status(status: object, notes: object) -> str | None:
    """Status with its notes, like v4's "ENTREGUE 1 LAMBIDA". The panel
    groups statuses by how they start, so the notes go after."""
    parts = [str(part) for part in (status, notes) if pd.notna(part)]

    return ' '.join(parts) or None


def load_sections(sections: list[str]) -> pd.DataFrame:
    sheets = _fetch_sheets()
    rows = split_untitled(_section_rows(sheets))
    rows = rows[rows['section'].isin(sections)].reset_index(drop=True)

    df = _join_contracts(rows, _contracts(sheets[CONTRACTS_SHEET]))

    for column in NUMERIC_COLUMNS:
        df[column] = df[column].map(parse_number).astype('Float64')

    # Whole years, though nothing stops the sheet from holding "2.5"
    df['term_years'] = (
        df['term_years'].map(parse_number).astype('Float64').round()
    ).astype('Int64')

    for column in DATE_COLUMNS:
        df[column] = pd.to_datetime(df[column].map(parse_date))

    for column in TEXT_COLUMNS:
        df[column] = df[column].map(parse_text).astype('string')

    df['term'] = pd.Series(
        map(_term, df['term_years'], df['term_notes']),
        index=df.index,
        dtype='string',
    )
    df['status'] = pd.Series(
        map(_status, df['status'], df['status_notes']),
        index=df.index,
        dtype='string',
    )

    df['check_status'] = _check_statuses(df['check'].astype('string'))

    return df[RESPONSE_COLUMNS]
