lazy from uuid import UUID

lazy from fastapi import HTTPException
lazy from sqlalchemy import select
lazy from sqlalchemy.exc import IntegrityError
lazy from sqlalchemy.ext.asyncio import AsyncSession

lazy from app.api.v2.modules.poles.licensed_poles.schemas import (
    LicensedPolesCreate,
    LicensedPolesUpdate,
)
lazy from app.modules.poles.licensed_poles.model import LicensedPoles


async def _verify_pole_duplicate(db, licensed):
    duplicate = await db.scalar(
        select(LicensedPoles).where(
            LicensedPoles.municipality == licensed.municipality,
            LicensedPoles.electric_power_carrier_id
            == licensed.electric_power_carrier_id,
        )
    )
    return duplicate


async def get_licensed_poles(db):
    result = await db.scalars(select(LicensedPoles))
    return result.all()


async def get_licensed_poles_by_id(db: AsyncSession, licensed_pole_id: UUID):
    result = await db.get(LicensedPoles, licensed_pole_id)
    if result is None:
        raise HTTPException(status_code=404, detail='municipal not found')
    return result


async def create_licensed_poles_service(
    db: AsyncSession, licensed_poles: LicensedPolesCreate
):
    if await _verify_pole_duplicate(db, licensed_poles):
        raise HTTPException(status_code=409, detail='municipal already exists')

    new_licensed_poles = LicensedPoles(**licensed_poles.model_dump())

    db.add(new_licensed_poles)
    await db.commit()
    await db.refresh(new_licensed_poles)

    return new_licensed_poles


async def update_licensed_poles(
    db: AsyncSession, licensed_pole_id: UUID, licensed: LicensedPolesUpdate
):
    updated_poles = await db.get(LicensedPoles, licensed_pole_id)

    if updated_poles is None:
        raise HTTPException(status_code=404, detail='municipal not found')

    changes = licensed.model_dump(exclude_unset=True)

    for field_name, field_value in changes.items():
        setattr(updated_poles, field_name, field_value)
    try:
        await db.commit()
        await db.refresh(updated_poles)

        return updated_poles

    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail='municipal already exists')


async def delete_licensed_poles(db: AsyncSession, licensed_pole_id: UUID):
    deleted_licensed = await db.get(LicensedPoles, licensed_pole_id)
    if not deleted_licensed:
        raise HTTPException(status_code=404, detail='municipal not found')
    await db.delete(deleted_licensed)
    await db.commit()

    return deleted_licensed
