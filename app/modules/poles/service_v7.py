from io import BytesIO

import pandas as pd
import requests
from app.core.settings import get_settings

settings = get_settings()
url = settings.POLES_V7_SHEET_URL


def get_df():
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return pd.read_excel(
        BytesIO(response.content), sheet_name='licenciados', engine='openpyxl'
    )


def load_viability_poles(
    pole_owners: list | None = None, df: pd.DataFrame = get_df()
) -> dict:
    treated_df = (
        df
        .groupby('CONCESSIONARIA')[
            ['MUNICIPIO', 'CODIGO IBGE', 'POSTES LICENCIADOS', 'VALOR']
        ]
        .apply(
            lambda pole_owner: pole_owner.set_index('MUNICIPIO').to_dict(
                orient='index'
            )
        )
        .to_dict()
    )

    if pole_owners is not None:
        return {
            pole_owner.upper(): treated_df[pole_owner.upper()]
            for pole_owner in pole_owners
        }
    return treated_df
