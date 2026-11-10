from fastapi import HTTPException
lazy import pandas as pd

lazy from app.core.constants import VIABILIDADE_SHEET_URL

REQUIRED_COLUMNS = {'TECNOLOGIA', 'CIDADE', 'ID CONTRATO'}


def _load_sheet():
    df = pd.read_csv(VIABILIDADE_SHEET_URL)

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise HTTPException(
            status_code=502,
            detail=f'Missing columns in sheet: {", ".join(sorted(missing))}',
        )

    return df[df['TECNOLOGIA'] != 'WIRELESS']


def _clients_by_city(df):
    return df.groupby('CIDADE')['ID CONTRATO'].nunique()


def get_clients_by_city():
    clients = _clients_by_city(_load_sheet())
    return [
        {'city': city, 'clients': int(total)}
        for city, total in clients.items()
    ]


def get_clients_by_city_name(city: str):
    clients = _clients_by_city(_load_sheet())
    city = city.strip().upper()

    if city not in clients:
        raise HTTPException(status_code=404, detail='City not found')

    return {'city': city, 'clients': int(clients[city])}


def get_technologies():
    technologies = _load_sheet()['TECNOLOGIA'].value_counts()
    return [
        {'technology': technology, 'total': int(total)}
        for technology, total in technologies.items()
    ]
