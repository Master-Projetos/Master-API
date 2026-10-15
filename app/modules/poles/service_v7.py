import logging
import unicodedata
from io import BytesIO

import pandas as pd
import requests

from app.core.constants import POLES_V7_SHEET_URL, POLES_V7_UTILITY_SHEETS

logger = logging.getLogger(__name__)

FETCH_TIMEOUT_SECONDS = 30

# CEMIG's licensed poles: one row per licensing project, exclusion
# projects carry negative pole counts
LICENSED_SHEET = 'MAPEAMENTO REDE LICENCIADA'
LICENSED_HEADER_ROW = 1
LICENSED_SHEET_UTILITY = 'CEMIG'

# Every pole of these utilities is licensed, so none is unlicensed
FULLY_LICENSED_UTILITIES = {'DME'}

# Rent per pole of each utility
GEOGRID_SHEET = 'BASE DE DADOS GEOGRID'

# Pivot tables behind each utility's dashboard: irregular poles and the
# total poles the network occupies
PIVOT_SHEET = 'Tabela Dinâmica'
IRREGULAR_POLES_LABEL = 'Soma de QNT. PONTOS IRREGULARES'
OCCUPIED_POLES_LABEL = 'Soma de POSTES'

# The other utilities come from their own tab's "CIDADES" table, which
# also holds the estimated poles the network uses per city
CITIES_LABEL = 'CIDADES'
TOTAL_LABEL = 'TOTAL'


def _fetch_workbook() -> dict[str, pd.DataFrame]:
    logger.info('Fetching poles v7 spreadsheet')
    response = requests.get(POLES_V7_SHEET_URL, timeout=FETCH_TIMEOUT_SECONDS)
    response.raise_for_status()

    return pd.read_excel(
        BytesIO(response.content),
        sheet_name=[LICENSED_SHEET, GEOGRID_SHEET, PIVOT_SHEET, *POLES_V7_UTILITY_SHEETS],
        header=None,
        engine='openpyxl',
    )


def _city_key(name) -> str:
    """Accent and case insensitive key, e.g. 'Itaúna' and 'ITAUNA' match."""
    text = unicodedata.normalize('NFKD', str(name)).encode('ascii', 'ignore')
    return ' '.join(text.decode().upper().split())


def _with_header(raw: pd.DataFrame, header_row: int) -> pd.DataFrame:
    labels = raw.iloc[header_row].astype(str).str.split().str.join(' ').str.lower()
    return raw.iloc[header_row + 1:].set_axis(labels, axis=1)


def _parse_licensed(raw: pd.DataFrame) -> pd.DataFrame:
    table = _with_header(raw, LICENSED_HEADER_ROW)
    table = table.rename(columns={'concessionária': 'utility', 'cidade': 'city'})
    table = table.dropna(subset=['utility', 'city'])
    table['utility'] = table['utility'].str.strip().str.upper()
    table['city'] = table['city'].str.strip()
    # "-" marks a project without a count
    table['postes'] = pd.to_numeric(table['postes'], errors='coerce').fillna(0)
    table['key'] = table['city'].map(_city_key)

    return table.groupby(['utility', 'key'], as_index=False).agg(
        city=('city', 'first'),
        licensed_poles=('postes', 'sum'),
        projects=('postes', 'size'),
    )


def _parse_rents(raw: pd.DataFrame) -> dict[str, float]:
    table = _with_header(raw, 0)
    rents = pd.to_numeric(table['valor do aluguel'], errors='coerce')
    utilities = table['concessionária'].astype(str).str.strip().str.upper()

    return rents.groupby(utilities).first().dropna().to_dict()


def _parse_cities_table(raw: pd.DataFrame) -> pd.DataFrame:
    """The "LICENCIAMENTO POR CIDADES" table of a utility tab.

    Labeled columns are city, quantity and value; the last unlabeled one is
    the estimated poles the network uses (network length / 35 m).
    """
    hits = raw.isin([CITIES_LABEL]).stack()
    hits = hits[hits]
    if hits.empty:
        raise ValueError(f'No "{CITIES_LABEL}" header found')
    header_row, city_col = hits.index[0]

    table = raw.loc[header_row + 1:, city_col:].dropna(axis=1, how='all')
    qty_col, value_col = table.columns[1], table.columns[2]
    unlabeled = [c for c in table.columns if pd.isna(raw.loc[header_row, c])]

    cities = table[city_col].astype('string').str.strip()
    end = cities.str.upper().eq(TOTAL_LABEL).idxmax() if cities.str.upper().eq(TOTAL_LABEL).any() else None
    table = table.loc[:end].iloc[:-1] if end is not None else table
    table = table[table[city_col].notna()]

    return pd.DataFrame({
        'key': table[city_col].map(_city_key),
        'city': table[city_col].astype(str).str.strip(),
        'licensed_poles': pd.to_numeric(table[qty_col], errors='coerce').fillna(0),
        'licensed_rent': pd.to_numeric(table[value_col], errors='coerce'),
        'network_poles': (
            pd.to_numeric(table[unlabeled[-1]], errors='coerce')
            if unlabeled else pd.NA
        ),
    })


def _utility_cities(sheets: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Licensed poles per city of each utility."""
    licensed = _parse_licensed(sheets[LICENSED_SHEET])
    tables = {}
    for utility in POLES_V7_UTILITY_SHEETS:
        cities = _parse_cities_table(sheets[utility])
        if utility == LICENSED_SHEET_UTILITY:
            network = cities.set_index('key')['network_poles']
            cities = licensed[licensed['utility'] == utility].drop(columns='utility')
            cities['network_poles'] = cities['key'].map(network)
            cities['licensed_rent'] = pd.NA
        else:
            cities['projects'] = pd.NA
        tables[utility] = cities

    return tables


def _parse_pivot(raw: pd.DataFrame, label: str) -> dict[str, tuple[float, float]]:
    """(poles, value) per utility of the pivot table whose poles column is
    `label`; the value is the column right after it."""
    hits = raw.isin([label]).stack()
    hits = hits[hits]
    if hits.empty:
        raise ValueError(f'No "{label}" pivot found in {PIVOT_SHEET}')
    header_row, poles_col = hits.index[0]
    utility_col = raw.columns[raw.columns.get_loc(poles_col) - 2]
    value_col = raw.columns[raw.columns.get_loc(poles_col) + 1]

    totals = {}
    for row in raw.loc[header_row + 1:].itertuples(index=False):
        utility = row[utility_col]
        if utility not in POLES_V7_UTILITY_SHEETS:
            break
        totals[utility] = (float(row[poles_col]), float(row[value_col]))

    return totals


def _optional(value) -> float | None:
    return None if pd.isna(value) else float(value)


def load_poles(utilities: list[str] | None = None) -> list[dict]:
    sheets = _fetch_workbook()
    rents = _parse_rents(sheets[GEOGRID_SHEET])
    irregular = _parse_pivot(sheets[PIVOT_SHEET], IRREGULAR_POLES_LABEL)
    occupied = _parse_pivot(sheets[PIVOT_SHEET], OCCUPIED_POLES_LABEL)
    tables = _utility_cities(sheets)

    if utilities:
        unknown = set(utilities) - set(tables)
        if unknown:
            raise LookupError(sorted(unknown))
        tables = {u: tables[u] for u in utilities}

    result = []
    for utility, group in tables.items():
        cities = []
        for row in group.sort_values('city').itertuples():
            licensed_poles = int(row.licensed_poles)
            # The utility tabs give the rent per city, CEMIG's comes from GEOGRID
            rent = _optional(row.licensed_rent)
            rent_per_pole = (
                rent / licensed_poles if rent is not None and licensed_poles
                else rents.get(utility)
            )
            if rent is None:
                rent = _money(licensed_poles, rent_per_pole)

            network_poles = _optional(row.network_poles)
            if utility in FULLY_LICENSED_UTILITIES:
                network_poles = float(licensed_poles)
            unlicensed_poles = (
                max(round(network_poles) - licensed_poles, 0)
                if network_poles is not None else None
            )
            cities.append({
                'city': row.city,
                'projects': None if pd.isna(row.projects) else int(row.projects),
                'rent_per_pole': round(rent_per_pole, 2) if rent_per_pole else None,
                'licensed_poles': licensed_poles,
                'licensed_rent': round(rent, 2) if rent is not None else None,
                'network_poles': round(network_poles) if network_poles is not None else None,
                'unlicensed_poles': unlicensed_poles,
                'unlicensed_rent': _money(unlicensed_poles, rent_per_pole),
            })

        result.append({
            'utility': utility,
            'rent_per_pole': rents.get(utility, cities[0]['rent_per_pole'] if cities else None),
            'licensed_poles': sum(c['licensed_poles'] for c in cities),
            'licensed_rent': round(sum(c['licensed_rent'] or 0 for c in cities), 2),
            # Utility totals as the dashboards show them, since not every
            # tab has a per city network estimate
            'unlicensed_poles': round(irregular.get(utility, (0, 0))[0]),
            'unlicensed_rent': round(irregular.get(utility, (0, 0))[1], 2),
            'occupied_poles': round(occupied[utility][0]) if utility in occupied else None,
            'occupied_rent': round(occupied[utility][1], 2) if utility in occupied else None,
            'cities': cities,
        })

    return result


def _money(poles: int | None, rent: float | None) -> float | None:
    if poles is None or rent is None:
        return None
    return round(poles * rent, 2)
