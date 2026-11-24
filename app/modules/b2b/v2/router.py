from http import HTTPStatus
from uuid import UUID

lazy from fastapi import APIRouter, HTTPException

from app.core.security import SessionDep
from app.modules.b2b.v2.services import (
    fetch_b2b_report,
    create_b2b_report,
    update_b2b_report,
    delete_b2b_report,
)
from app.modules.b2b.v2.schemas import B2bCreate, B2bUpdate


b2b_router = APIRouter()


@b2b_router.get('/get')
async def get_b2b_record(session: SessionDep):
    return {'records': await fetch_b2b_report(session)}


@b2b_router.post('/post')
async def post_b2b_record(b2b_data: B2bCreate, session: SessionDep):
    try:
        return await create_b2b_report(session, b2b_data)
    except ValueError as error:
        raise HTTPException(status_code=HTTPStatus.CONFLICT, detail=str(error))


@b2b_router.patch('/patch')
async def patch_b2b_record(
    session: SessionDep, b2b_data: B2bUpdate, b2b_id: UUID
):
    try:
        return await update_b2b_report(
            session=session, b2b_data=b2b_data, report_id=b2b_id
        )
    except ValueError as error:
        raise HTTPException(status_code=HTTPStatus.CONFLICT, detail=str(error))


@b2b_router.delete('/delete')
async def delete_b2b_record(session: SessionDep, b2b_id: UUID):
    return await delete_b2b_report(session, b2b_id)
