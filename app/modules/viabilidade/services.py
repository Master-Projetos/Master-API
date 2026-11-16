import logging
import threading
import time

from fastapi import HTTPException
lazy import pandas as pd

lazy from app.core.constants import VIABILIDADE_SHEET_URL

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {
    'CIDADE',
    'BAIRRO CONEXÃO',
    'ID CONTRATO',
    'TECNOLOGIA',
    'VALOR SEM ADITIVOS',
}

CACHE_TTL_SECONDS = 600

_cache_lock = threading.Lock()
_cache: dict = {'report': None, 'at': 0.0}


def _normalize(column):
    return (
        column.str.normalize('NFKD')
        .str.encode('ascii', errors='ignore')
        .str.decode('ascii')
        .str.replace(r'[\x00-\x1f]', '', regex=True)
        .str.replace(r'\s+', ' ', regex=True)
        .str.strip()
        .str.upper()
    )


def _load_sheet_clean():
    # The sheet has ~250k rows and 22 columns; loading only the used ones
    # keeps the frame around 16 MB instead of 200+ MB.
    df = pd.read_csv(
        VIABILIDADE_SHEET_URL,
        usecols=lambda column: column in REQUIRED_COLUMNS,
        dtype=str,
    )

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise HTTPException(
            status_code=502,
            detail=f'Missing columns in sheet: {", ".join(sorted(missing))}',
        )

    neighborhood_df = pd.read_csv('data/neighborhood.csv')

    df['CIDADE'] = _normalize(df['CIDADE'])
    df['BAIRRO CONEXÃO'] = _normalize(df['BAIRRO CONEXÃO'])

    df = df.merge(neighborhood_df, on=['CIDADE', 'BAIRRO CONEXÃO'], how='left')
    df['BAIRRO CONEXÃO'] = df['BAIRRO PADRAO'].fillna(df['BAIRRO CONEXÃO'])
    df = df.drop(columns='BAIRRO PADRAO')

    return df


def _unique_contracts(df):
    # Each row is a contract item, so the wireless flag and the value are
    # aggregated per contract before dropping the duplicated rows.
    contract = df['ID CONTRATO']
    wireless = (
        df['TECNOLOGIA'].eq('WIRELESS').groupby(contract).transform('any')
    )
    value = pd.to_numeric(
        df['VALOR SEM ADITIVOS']
        .astype(str)
        .str.replace('.', '', regex=False)
        .str.replace(',', '.', regex=False),
        errors='coerce',
    ).fillna(0)

    return df.assign(
        WIRELESS=wireless,
        VALUE=value.groupby(contract).transform('sum'),
        **{'BAIRRO CONEXÃO': df['BAIRRO CONEXÃO'].fillna('NAO INFORMADO')},
    ).drop_duplicates('ID CONTRATO')


def _revenue(contracts):
    revenue = float(contracts['VALUE'].sum())
    return {
        'clients': len(contracts),
        'revenue': round(revenue, 2),
        'average_ticket': round(revenue / len(contracts), 2),
    }


def _count(contracts):
    wireless = int(contracts['WIRELESS'].sum())
    return {
        **_revenue(contracts),
        'wireless': wireless,
        'non_wireless': len(contracts) - wireless,
    }


def _clients_by_city(contracts):
    return {
        city: {
            'city': city,
            **_count(group),
            'neighborhoods': {
                neighborhood: _count(items)
                for neighborhood, items in group.groupby('BAIRRO CONEXÃO')
            },
        }
        for city, group in contracts.groupby('CIDADE')
    }


def _wireless_clients_by_city(contracts):
    contracts = contracts[contracts['WIRELESS']]
    return {
        city: {
            'city': city,
            **_revenue(group),
            'neighborhoods': {
                neighborhood: _revenue(items)
                for neighborhood, items in group.groupby('BAIRRO CONEXÃO')
            },
        }
        for city, group in contracts.groupby('CIDADE')
    }


def _build_report():
    df = _load_sheet_clean()
    technologies = df.loc[
        df['TECNOLOGIA'] != 'WIRELESS', 'TECNOLOGIA'
    ].value_counts()
    contracts = _unique_contracts(df)
    del df

    return {
        'cities': _clients_by_city(contracts),
        'wireless_cities': _wireless_clients_by_city(contracts),
        'technologies': [
            {'technology': technology, 'total': int(total)}
            for technology, total in technologies.items()
        ],
    }


def _get_report():
    # Only the aggregated dicts are cached, and the lock makes concurrent
    # requests wait for a single sheet load instead of each loading a copy.
    with _cache_lock:
        if (
            _cache['report'] is not None
            and time.monotonic() - _cache['at'] < CACHE_TTL_SECONDS
        ):
            return _cache['report']

        try:
            _cache['report'] = _build_report()
            _cache['at'] = time.monotonic()
        except Exception:
            if _cache['report'] is None:
                raise
            logger.exception(
                'failed to refresh the viabilidade sheet, using cached copy'
            )
        return _cache['report']


def _find_city(clients, city):
    city = _normalize(pd.Series([city]))[0]

    if city not in clients:
        raise HTTPException(status_code=404, detail='City not found')

    return clients[city]


def get_clients_by_city():
    return list(_get_report()['cities'].values())


def get_clients_by_city_name(city: str):
    return _find_city(_get_report()['cities'], city)


def get_wireless_clients_by_city():
    return list(_get_report()['wireless_cities'].values())


def get_wireless_clients_by_city_name(city: str):
    return _find_city(_get_report()['wireless_cities'], city)


def get_technologies():
    return _get_report()['technologies']
