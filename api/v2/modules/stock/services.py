import logging
import re
from datetime import date

import numpy as np
import pandas as pd

from core.constants import STOCK_SHEET_URL

logger = logging.getLogger(__name__)

# The header spans two rows (site names above, column labels below) and sits
# under a title, so its position is found by looking for this label
HEADER_LABEL = 'Descrição'

# Columns shared by every site, mapped to their name in the response
ITEM_COLUMNS = {
    'Codmat': 'code',
    'Descrição': 'description',
    'Unid.': 'unit',
    'ESTOQUE MÍNIMO': 'min_stock',
    'TOTAL': 'total',
}

TEXT_COLUMNS = ('code', 'description', 'unit')
NUMERIC_COLUMNS = ('min_stock', 'total', 'balance')

# Balance labels vary ("SALDO", "Saldo CD", "SALDO LAVRAS"), so only their
# prefix is matched
BALANCE_LABEL_PREFIX = 'SALDO'

# Short code of each site, so it fits in a chart legend. Divinópolis is the CD
SITE_CODES = {
    'DIVINOPOLIS': 'CD',
    'LAVRAS': 'LAV',
    'TAUBATE': 'TAU',
    'UNAI': 'UNA',
    'MONTES CLAROS': 'MOC',
}

# The safe stock is the minimum stock plus this fraction of it
SAFE_STOCK_MARGIN = 0.3

# Alert level of each row in the per-site breakdown
LEVEL_OK = 'ok'
LEVEL_ALERT = 'alert'
LEVEL_CRITICAL = 'critical_alert'
LEVEL_NO_MINIMUM = 'no_minimum'

RESPONSE_COLUMNS = [
    'site',
    'code',
    'description',
    'unit',
    'min_stock',
    'safe_stock',
    'balance',
    'alert',
    'critical_alert',
    'total',
]

# The restock schedule sits in the same tab as the stock table. Its header
# starts with this label, followed by one column per month
RESTOCK_HEADER_LABEL = 'REGIONAL'
# The schedule title, one row above the header, holds the year: "... (2026)"
RESTOCK_TITLE_KEYWORD = 'REPOSI'

MONTHS = {
    'JANEIRO': 1,
    'FEVEREIRO': 2,
    'MARÇO': 3,
    'MARCO': 3,
    'ABRIL': 4,
    'MAIO': 5,
    'JUNHO': 6,
    'JULHO': 7,
    'AGOSTO': 8,
    'SETEMBRO': 9,
    'OUTUBRO': 10,
    'NOVEMBRO': 11,
    'DEZEMBRO': 12,
}

# A cell lists its windows split by "-", like "01 A 02/10 - 19 A 20/10".
# Each window is a day range ("14 a 15/10", "30/09 a 02/10") or a single day
WINDOW_SEPARATOR = '-'
DAY_RANGE_PATTERN = re.compile(
    r'^(\d{1,2})(?:/(\d{1,2}))?\s*(?:A|ATÉ|ATE)\s*(\d{1,2})/(\d{1,2})$',
    re.IGNORECASE,
)
SINGLE_DAY_PATTERN = re.compile(r'^(\d{1,2})/(\d{1,2})$')


def parse_ptbr_integers(values: pd.Series) -> pd.Series:
    """Parse pt-BR formatted numbers, where '15.000' is fifteen thousand.

    Every quantity is a whole number, and a blank cell becomes NA.
    """
    normalized = (
        values.str
        .strip()
        .str.replace('.', '', regex=False)
        .str.replace(',', '.', regex=False)
    )

    return pd.to_numeric(normalized, errors='coerce').astype('Int64')


def _get_site_code(site_name: str) -> str:
    """Short code of a site, falling back to its first letters if unknown."""
    code = SITE_CODES.get(site_name)
    if code is None:
        code = site_name[:3].upper()
        logger.warning('Site "%s" has no code, using "%s"', site_name, code)

    return code


def _find_header_row(raw: pd.DataFrame) -> int:
    """Index of the row that holds the column labels."""
    matches = raw.index[raw.eq(HEADER_LABEL).any(axis=1)]
    if matches.empty:
        raise ValueError(f'No header row containing "{HEADER_LABEL}"')

    return matches[0]


def _find_balance_columns(
    labels: pd.Series, site_names: pd.Series
) -> dict[str, int]:
    """Map each site name to the position of its balance column."""
    balance_columns = {}

    for position, label in labels.items():
        site_name = site_names.get(position)
        if pd.isna(site_name) or pd.isna(label):
            continue

        if label.upper().startswith(BALANCE_LABEL_PREFIX):
            balance_columns[site_name] = position

    # A renamed label would silently drop a site from the response. The last
    # group in the header is not a site, so it is not expected to have one
    last_group = site_names.iloc[-1]
    missing_sites = (
        set(site_names.dropna()) - set(balance_columns) - {last_group}
    )
    if missing_sites:
        logger.warning('No balance column for: %s', sorted(missing_sites))

    return balance_columns


def _add_alert_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Flag balances at or below the safe stock, and at or below the minimum.

    The safe stock is rounded up, since a fraction of a unit is useless.
    Items without a minimum cannot be judged, so their alerts are NA
    instead of a false all-clear.
    """
    min_stock = df['min_stock'].astype('Float64')
    df['safe_stock'] = np.ceil(min_stock * (1 + SAFE_STOCK_MARGIN)).astype(
        'Int64'
    )

    df['alert'] = (df['balance'] < df['safe_stock']) | (
        df['balance'] == df['min_stock']
    )
    df['critical_alert'] = df['balance'] < df['min_stock']

    return df


def _fetch_sheet() -> pd.DataFrame:
    """Download the stock tab as raw text cells, without any header."""
    logger.info('Fetching stock spreadsheet')
    # Read everything as text, since the numbers are pt-BR formatted
    return pd.read_csv(STOCK_SHEET_URL, header=None, dtype=str)


def _find_restock_header(raw: pd.DataFrame) -> tuple[int, int] | None:
    """Row and column of the restock schedule header, if the tab has one.

    The label alone could appear elsewhere, so a month name must follow it.
    """
    cells = raw.apply(lambda column: column.str.strip().str.upper())

    for row, column in zip(
        *np.nonzero(cells.eq(RESTOCK_HEADER_LABEL).to_numpy())
    ):
        next_label = (
            cells.iat[row, column + 1] if column + 1 < cells.shape[1] else None
        )
        if next_label in MONTHS:
            return int(row), int(column)

    return None


def _find_restock_title_row(raw: pd.DataFrame, header_row: int) -> int | None:
    """Closest row above the restock header holding the schedule title."""
    for row in range(header_row - 1, -1, -1):
        cells = raw.iloc[row].dropna().str.upper()
        if cells.str.contains(RESTOCK_TITLE_KEYWORD).any():
            return row

    return None


def _stock_body_end(
    raw: pd.DataFrame, header_row: int, last_column: int
) -> int:
    """Row where the stock table ends.

    The restock schedule shares the tab, so when it sits below the stock
    table, within its columns, its rows must not be read as items.
    """
    restock_header = _find_restock_header(raw)
    if restock_header is None:
        return len(raw)

    restock_row, restock_column = restock_header
    if restock_row <= header_row or restock_column > last_column:
        return len(raw)

    title_row = _find_restock_title_row(raw, restock_row)
    if title_row is not None and title_row > header_row:
        return title_row

    return restock_row


def load_stock_data() -> pd.DataFrame:
    """Download the stock sheet and return one row per item and site."""
    raw = _fetch_sheet()

    header_row = _find_header_row(raw)
    # A merged site cell only fills the first column it spans
    site_names = raw.iloc[header_row - 1].ffill().str.strip()
    labels = raw.iloc[header_row].str.strip()
    body_end = _stock_body_end(raw, header_row, labels.last_valid_index())
    body = raw.iloc[header_row + 1 : body_end].reset_index(drop=True)

    item_data = {
        ITEM_COLUMNS[label]: body[position]
        for position, label in labels.items()
        if label in ITEM_COLUMNS
    }
    missing_columns = set(ITEM_COLUMNS.values()) - set(item_data)
    if missing_columns:
        raise ValueError(
            f'Missing columns in the sheet: {sorted(missing_columns)}'
        )

    # Unpivot the balance column of each site into its own set of rows
    site_frames = []
    for site_name, position in _find_balance_columns(
        labels, site_names
    ).items():
        site_df = pd.DataFrame(item_data)
        site_df['site'] = _get_site_code(site_name)
        site_df['balance'] = body[position]
        site_frames.append(site_df)

    df = pd.concat(site_frames, ignore_index=True)

    # The sheet has blank rows below the table
    df = df[df['description'].notna()]

    # Codmat is an identifier, so it stays as text to keep leading zeros
    for column in TEXT_COLUMNS:
        df[column] = df[column].str.strip()

    for column in NUMERIC_COLUMNS:
        df[column] = parse_ptbr_integers(df[column])

    df = _add_alert_columns(df)

    return df[RESPONSE_COLUMNS].reset_index(drop=True)


def _to_records(df: pd.DataFrame) -> list[dict]:
    """Rows as dicts, with missing values as None instead of NA."""
    records = df.astype(object).where(df.notna(), None)

    return records.to_dict(orient='records')


def get_summary(df: pd.DataFrame) -> dict:
    """Overall totals of items, sites and alerts."""
    return {
        'total_items': int(df['code'].nunique()),
        'total_sites': int(df['site'].nunique()),
        'alert_rows': int(df['alert'].sum()),
        'critical_alert_rows': int(df['critical_alert'].sum()),
    }


def get_alerts_by_site(df: pd.DataFrame) -> dict:
    """Row count of each site per alert level, using the worst level that applies."""
    levels = pd.Series(LEVEL_OK, index=df.index)
    levels[df['alert'].fillna(False)] = LEVEL_ALERT
    levels[df['critical_alert'].fillna(False)] = LEVEL_CRITICAL
    # Items without a minimum were never judged, so they are not "ok"
    levels[df['min_stock'].isna()] = LEVEL_NO_MINIMUM

    return pd.crosstab(df['site'], levels).to_dict()


def get_dashboard(df: pd.DataFrame) -> dict:
    """Full payload of the stock dashboard endpoint."""
    return {
        'summary': get_summary(df),
        'alerts_by_site': get_alerts_by_site(df),
        'items': _to_records(df),
    }


def _parse_restock_year(raw: pd.DataFrame, header_row: int) -> int:
    """Year in the schedule title, or the current one if it is missing."""
    title_row = _find_restock_title_row(raw, header_row)
    if title_row is not None:
        title = ' '.join(raw.iloc[title_row].dropna())
        if match := re.search(r'\b(20\d{2})\b', title):
            return int(match.group(1))

    year = date.today().year
    logger.warning('Restock schedule title has no year, using %s', year)

    return year


def _parse_window(text: str, year: int) -> dict | None:
    """Start and end dates of a window like "14 a 15/10", or None if unknown."""
    if match := DAY_RANGE_PATTERN.match(text):
        start_day, start_month, end_day, end_month = match.groups()
        start_month = start_month or end_month
    elif match := SINGLE_DAY_PATTERN.match(text):
        start_day, start_month = match.groups()
        end_day, end_month = start_day, start_month
    else:
        return None

    try:
        start = date(year, int(start_month), int(start_day))
        # A window like "30/12 a 02/01" ends in the next year
        end_year = year + 1 if int(start_month) > int(end_month) else year
        end = date(end_year, int(end_month), int(end_day))
    except ValueError:
        return None

    return {'start': start, 'end': end}


def _parse_windows(
    cell: str | float, year: int
) -> tuple[str | None, list[dict]]:
    """Cell text and the windows it lists. Unreadable windows are logged."""
    if pd.isna(cell) or not cell.strip():
        return None, []

    text = cell.strip()
    windows = []
    for part in text.split(WINDOW_SEPARATOR):
        window = _parse_window(part.strip(), year)
        if window is None:
            logger.warning(
                'Could not read restock window "%s" in "%s"',
                part.strip(),
                text,
            )
            continue
        windows.append(window)

    return text, windows


def load_restock_schedule() -> dict:
    """Download the stock sheet and return its restock schedule."""
    raw = _fetch_sheet()

    restock_header = _find_restock_header(raw)
    if restock_header is None:
        raise ValueError(
            f'No restock schedule header "{RESTOCK_HEADER_LABEL}"'
        )

    header_row, region_column = restock_header
    year = _parse_restock_year(raw, header_row)

    # Months run to the right of the region label, up to the first other cell
    month_columns = []
    for column in range(region_column + 1, raw.shape[1]):
        label = raw.iat[header_row, column]
        month = (
            MONTHS.get(label.strip().upper())
            if isinstance(label, str)
            else None
        )
        if month is None:
            break
        month_columns.append((column, month, label.strip()))

    regions = []
    for row in range(header_row + 1, len(raw)):
        region = raw.iat[row, region_column]
        # The table ends at the first row without a region
        if pd.isna(region) or not region.strip():
            break

        months = []
        for column, month, label in month_columns:
            text, windows = _parse_windows(raw.iat[row, column], year)
            months.append({
                'month': month,
                'label': label,
                'text': text,
                'windows': windows,
            })

        regions.append({'region': region.strip(), 'months': months})

    return {'year': year, 'regions': regions}
