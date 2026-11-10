import logging
import threading
import time
from io import BytesIO

import pandas as pd
import requests
from app.core.settings import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()
url = settings.POLES_V7_SHEET_URL

CACHE_TTL_SECONDS = 600

_cache_lock = threading.Lock()
_cached_df: pd.DataFrame | None = None
_cached_at: float = 0.0


class UnknownPoleOwnersError(Exception):
    pass


def get_df():
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return pd.read_excel(
        BytesIO(response.content), sheet_name='licenciados', engine='openpyxl'
    )


def get_cached_df() -> pd.DataFrame:
    global _cached_df, _cached_at

    with _cache_lock:
        if (
            _cached_df is not None
            and time.monotonic() - _cached_at < CACHE_TTL_SECONDS
        ):
            return _cached_df

        try:
            _cached_df = get_df()
            _cached_at = time.monotonic()
        except Exception:
            if _cached_df is None:
                raise
            logger.exception(
                'failed to refresh the poles v7 spreadsheet, using cached copy'
            )
        return _cached_df


def load_viability_poles(
    pole_owners: list | None = None, df: pd.DataFrame | None = None
) -> dict:
    if df is None:
        df = get_cached_df()

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
        requested = [pole_owner.upper() for pole_owner in pole_owners]
        unknown = [owner for owner in requested if owner not in treated_df]
        if unknown:
            raise UnknownPoleOwnersError(unknown)
        return {owner: treated_df[owner] for owner in requested}
    return treated_df
