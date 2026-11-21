lazy import pandas as pd
lazy from sqlalchemy import delete, insert
lazy from sqlalchemy.orm import Session
lazy from app.modules.geogrid.v2.viability.model import ViabilityModel
lazy from app.modules.geogrid.v2.client import fetch_geogrid_report
lazy from app.modules.geogrid.v2.viability.constants import (
    COLUMNS,
    NUMERIC_COLUMNS,
)


async def sync_viability_record(session: Session):
    records = fetch_geogrid_report(
        'viabilidade',
        items='terminal',
    )

    df = pd.DataFrame(records, columns=COLUMNS)
    df[NUMERIC_COLUMNS] = df[NUMERIC_COLUMNS].apply(pd.to_numeric)
    df = df.rename(columns={'descricaoRecipienteTipo': 'tipo'})

    df = df.astype(object).where(df.notna(), None)

    records = df.to_dict(orient='records')

    await session.execute(delete(ViabilityModel))
    await session.execute(insert(ViabilityModel), records)
    await session.commit()

    return len(records)
