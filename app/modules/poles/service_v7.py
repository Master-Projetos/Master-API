from io import BytesIO

import pandas as pd
import requests
from app.core.settings import get_settings

settings = get_settings()
url = settings.POLES_V7_SHEET_URL
 
def get_df():
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return pd.read_excel(BytesIO(response.content), sheet_name='licenciados', engine='openpyxl')


def load_viability_poles(names: list = None, df: pd.DataFrame = get_df()) -> dict:
    treated_df = df.groupby('CONCESSIONARIA')[['MUNICIPIO', 'CODIGO IBGE', 'POSTES LICENCIADOS', 'VALOR']].apply(
        lambda x : x.set_index('MUNICIPIO').to_dict(orient='index')
    ).to_dict()
    
    if names != None:
        return treated_df[names]
    return treated_df