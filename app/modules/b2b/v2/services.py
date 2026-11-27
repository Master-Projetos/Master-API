from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.b2b.v2.model import B2bModel
from app.modules.b2b.v2.schemas import B2bCreate, B2bUpdate


async def fetch_b2b_report(session: AsyncSession) -> list[B2bModel]:
    records = await session.scalars(select(B2bModel))
    return list(records.all())


async def create_b2b_report(
    session: AsyncSession, b2b_data: B2bCreate
) -> B2bModel:
    report_link = str(b2b_data.report_link)

    duplicate_report = await session.scalar(
        select(B2bModel).where(B2bModel.report_link == report_link)
    )

    if duplicate_report:
        raise ValueError('Report already exists.')

    report_data = b2b_data.model_dump()
    report_data['report_link'] = report_link

    new_b2b_report = B2bModel(**report_data)

    session.add(new_b2b_report)
    await session.commit()
    await session.refresh(new_b2b_report)

    return new_b2b_report


async def update_b2b_report(
    session: AsyncSession, 
    b2b_data: B2bUpdate, 
    report_id: UUID
) -> B2bModel:
    target_report = await session.get(B2bModel, report_id)

    if not target_report:
        raise HTTPException(status_code=404, detail='this report dont exists')

    updated_fields = b2b_data.model_dump(exclude_unset=True)

    if 'report_link' in updated_fields:
        report_link = str(b2b_data.report_link)

        duplicate_report = await session.scalar(
            select(B2bModel).where(
                B2bModel.report_link == report_link,
                B2bModel.id != report_id,
            )
        )

        if duplicate_report:
            raise ValueError('Report already exists.')

        updated_fields['report_link'] = report_link

    for field, value in updated_fields.items():
        setattr(target_report, field, value)

    await session.commit()
    await session.refresh(target_report)
    return target_report


async def delete_b2b_report(session: AsyncSession, report_id: UUID) -> None:
    deleted_report = await session.get(B2bModel, report_id)

    if not deleted_report:
        raise HTTPException(status_code=404, detail='this report dont exists')

    await session.delete(deleted_report)
    await session.commit()
