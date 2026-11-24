import asyncio
lazy import pandas as pd
lazy from sqlalchemy import delete, insert, select
lazy from sqlalchemy.orm import Session
lazy from app.modules.geogrid.v2.viability.model import ViabilityModel
lazy from app.modules.geogrid.v2.client import fetch_geogrid_report
lazy from app.modules.geogrid.v2.viability.constants import (
    COLUMNS,
    NUMERIC_COLUMNS,
)


viability_cache = None


def _download_and_prepare():
    records = fetch_geogrid_report(
        'viabilidade',
        items='terminal',
    )

    df = pd.DataFrame(records, columns=COLUMNS)
    df[NUMERIC_COLUMNS] = df[NUMERIC_COLUMNS].apply(pd.to_numeric)
    df = df.rename(columns={'descricaoRecipienteTipo': 'tipo'})

    df = df.astype(object).where(df.notna(), None)

    return df.to_dict(orient='records')


async def fetch_viability_record(session: Session):
    global viability_cache

    if viability_cache is not None:
        return viability_cache

    result = await session.scalars(select(ViabilityModel))

    viability_cache = list(result.all())
    return viability_cache


async def sync_viability_record(session: Session):
    records = await asyncio.to_thread(_download_and_prepare)

    await session.execute(delete(ViabilityModel))
    await session.execute(insert(ViabilityModel), records)
    await session.commit()

    # Clear the cache instead of filling it with `records`: the next fetch reloads
    # from the database, so the response includes DB-generated columns (id, defaults)
    # and DB-converted types, keeping the same format the front receives after a restart.

    global viability_cache
    viability_cache = None

    return len(records)
