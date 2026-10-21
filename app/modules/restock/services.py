from uuid import UUID

from fastapi import HTTPException
lazy from sqlalchemy import select
lazy from app.modules.restock.model import Restock
lazy from app.api.v2.modules.restock.schemas import RestockCreate


async def _verify_duplicate(db, restock):
    duplicate = await db.scalar(
        select(Restock).where(
            Restock.end_date == restock.end_date,
            Restock.start_date == restock.start_date,
        )
    )
    return duplicate


async def get_restocks(db):
    result = await db.scalars(select(Restock))
    return result.all()


async def get_restock_by_id(db, restock_id: UUID):
    restock = await db.get(Restock, restock_id)
    if restock is None:
        raise HTTPException(status_code=404, detail='Restock not found')

    return restock


async def create_restock_service(db, restock_data: RestockCreate):
    if await _verify_duplicate(db, restock_data):
        raise HTTPException(status_code=409, detail='Restock already exists')

    new_restock = Restock(**restock_data.model_dump())
    db.add(new_restock)
    await db.commit()
    await db.refresh(new_restock)

    return new_restock


async def update_restock_service(db, restock_id, restock_data):
    restock = await get_restock_by_id(db, restock_id)

    changes = restock_data.model_dump(exclude_unset=True)
    start_date = changes.get('start_date', restock.start_date)
    end_date = changes.get('end_date', restock.end_date)
    if start_date > end_date:
        raise HTTPException(
            status_code=422, detail='start_date must be before end_date'
        )

    for field_name, field_value in changes.items():
        setattr(restock, field_name, field_value)

    await db.commit()
    await db.refresh(restock)

    return restock


async def delete_restock_service(db, restock_id):
    restock = await db.get(Restock, restock_id)
    if restock is None:
        raise HTTPException(status_code=404, detail='Restock not found')
    await db.delete(restock)
    await db.commit()
