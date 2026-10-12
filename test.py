import pandas as pd

from app.core.settings import get_settings

SETTINGS = get_settings()

stock_url = SETTINGS.STOCK_SHEET_URL

df = pd.read_csv(stock_url, header=3)

print(df.columns)

print()

print(df.head())

MINIMAL_STOCK_DELETE = ['Codmat', 'Unid.', 'Saldo CD',
       'REPOSIÇÃO REGIONAL', 'SALDO LAVRAS', 'REPOSIÇÃO REGIONAL.1',
       'SALDO TAUBATE', 'REPOSIÇÃO REGIONAL.2', 'SALDO UNAI',
       'REPOSIÇÃO REGIONAL.3', 'SALDO MONTES CLAROS', 'REPOSIÇÃO REGIONAL.4',
       'TOTAL']

df = df.drop(columns=MINIMAL_STOCK_DELETE)
print(df.head())