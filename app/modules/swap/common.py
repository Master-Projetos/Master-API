import logging
import re
from datetime import datetime

import pandas as pd

logger = logging.getLogger(__name__)

# How far each circuit was checked
CHECKED = 'checked'
MISSING_INFO = 'missing_info'
UNCHECKED = 'unchecked'
CHECK_STATUSES = [CHECKED, MISSING_INFO, UNCHECKED]

# Dark fiber, trunk and transport share one table, told apart by their
# agreement. "1 F.O" is a single optical fiber
UNTITLED_SECTION = 'untitled'
AGREEMENT_SECTIONS = {
    'FIBRA': 'dark-fiber',
    '1 F.O': 'dark-fiber',
    'ENTRONCAMENTO': 'trunk',
    'TRANSPORTE': 'transport',
}
# Rows with no agreement can't be told apart yet
UNDEFINED_SECTION = 'to-define'

DATE_COLUMNS = ('signed_at', 'ends_at')

# Some distances have a note after them, like "1280 (Aérea)"
LEADING_NUMBER_PATTERN = re.compile(r'^\s*(\d+(?:[.,]\d+)?)')


def clean_text(value: object) -> object:
    """Cells are full of line breaks and stray spaces."""
    if not isinstance(value, str):
        return value

    text = ' '.join(value.split())
    return text or pd.NA


def parse_number(value: object) -> float | None:
    """Cells also hold "?", notes and stray dates, which become None."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return None if pd.isna(value) else float(value)

    if isinstance(value, str) and (
        match := LEADING_NUMBER_PATTERN.match(value)
    ):
        return float(match.group(1).replace(',', '.'))

    return None


def parse_date(value: object) -> pd.Timestamp | None:
    """Some date cells hold notes like "FAZER ADITIVO" instead."""
    if isinstance(value, datetime):
        return pd.Timestamp(value)

    return None


def parse_text(value: object) -> str | None:
    """Excel gives whole numbers a ".0" that doesn't belong in text."""
    if pd.isna(value):
        return None

    if isinstance(value, float) and value.is_integer():
        return str(int(value))

    return str(value)


def _agreement_section(agreement: str | None) -> str | None:
    if isinstance(agreement, str):
        for prefix, section in AGREEMENT_SECTIONS.items():
            if agreement.upper().startswith(prefix):
                return section

    return None


def split_untitled(df: pd.DataFrame) -> pd.DataFrame:
    """Give each row of the untitled table the section of its agreement."""
    untitled = df['section'].eq(UNTITLED_SECTION)
    df.loc[untitled, 'section'] = df.loc[untitled, 'agreement'].map(
        _agreement_section
    )

    # A new kind of agreement is logged, so it gets its own section
    unknown = untitled & df['section'].isna() & df['agreement'].notna()
    for _, row in df[unknown].iterrows():
        logger.warning(
            'Swap row "%s" has unknown agreement "%s"',
            row['circuit'],
            row['agreement'],
        )

    df.loc[untitled & df['section'].isna(), 'section'] = UNDEFINED_SECTION

    return df


def to_records(df: pd.DataFrame) -> list[dict]:
    """Rows as dicts, with dates instead of timestamps and None for NA."""
    df = df.copy()
    for column in DATE_COLUMNS:
        df[column] = df[column].dt.date

    records = df.astype(object).where(df.notna(), None)

    return records.to_dict(orient='records')


def get_summary(df: pd.DataFrame) -> dict:
    """Overall totals of circuits, contracts and partners."""
    return {
        'total_circuits': len(df),
        'total_contracts': int(df['contract_id'].nunique()),
        'total_partners': int(df['partner'].nunique()),
        # Float sums leave noise like 8488.030999999999
        'total_fiber_km': round(float(df['fiber_km'].sum()), 2),
    }


def get_check_counts(df: pd.DataFrame) -> dict:
    """Circuit count per check status."""
    counts = df['check_status'].value_counts()

    return {status: int(counts.get(status, 0)) for status in CHECK_STATUSES}


def _check_counts_by(df: pd.DataFrame, column: str) -> dict:
    """Circuit count of each value of `column` per check status."""
    # Every status is listed, even at zero, so clients don't miss keys
    counts = pd.crosstab(df[column], df['check_status']).reindex(
        columns=CHECK_STATUSES, fill_value=0
    )

    return counts.to_dict(orient='index')


def get_by_section(df: pd.DataFrame) -> dict:
    return _check_counts_by(df, 'section')


def get_by_partner(df: pd.DataFrame) -> dict:
    return _check_counts_by(df, 'partner')


def get_dashboard(df: pd.DataFrame) -> dict:
    """Full payload of the swap endpoints."""
    return {
        'summary': get_summary(df),
        'check_counts': get_check_counts(df),
        'by_section': get_by_section(df),
        'by_partner': get_by_partner(df),
        'items': to_records(df),
    }
