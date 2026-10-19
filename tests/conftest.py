import os

# Set before the app is imported: environment variables win over .env, so the
# tests never see the real database
os.environ.update({
    'DEBUG': 'false',
    'SECRET_KEY': 'test',
    'GEOGRID_USER': 'test',
    'GEOGRID_PASSWORD': 'test',
    'DATABASE_URL': 'sqlite+aiosqlite://',
    'B2B_SHEET_URL': 'http://localhost/b2b',
    'STOCK_SHEET_URL': 'http://localhost/stock',
    'SWAP_V5_SHEET_URL': 'http://localhost/swap',
    'STOCK_V6_SHEET_URL': 'http://localhost/stock6',
    'POLES_V7_SHEET_URL': 'http://localhost/poles',
})
