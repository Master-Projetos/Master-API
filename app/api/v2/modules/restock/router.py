from typing import List
from uuid import UUID

lazy from fastapi import APIRouter, Security

lazy from app.core.security import SessionDep, require_scope
lazy from app.modules.api_key.model import Scope
lazy from app.api.v2.modules.restock.schemas import (
    RestockGet,
    RestockCreate,
    RestockUpdate,
)
lazy from app.modules.restock.services import (
    get_restocks,
    get_restock_by_id,
    create_restock_service,
    update_restock_service,
    delete_restock_service,
)

restock_router = APIRouter(
    dependencies=[Security(require_scope(Scope.RESTOCK_READ))]
)


@restock_router.get('/', response_model=List[RestockGet])
async def read_all_restocks(session: SessionDep):
    return await get_restocks(session)


@restock_router.get('/{restock_id}', response_model=RestockGet)
async def get_restock(restock_id: UUID, session: SessionDep):
    return await get_restock_by_id(session, restock_id)


@restock_router.post(
    '/',
    response_model=RestockGet,
    status_code=201,
    dependencies=[Security(require_scope(Scope.RESTOCK_WRITE))],
)
async def create_restock(
    restock_create: RestockCreate,
    session: SessionDep,
):
    return await create_restock_service(session, restock_create)


@restock_router.patch(
    '/{restock_id}',
    response_model=RestockGet,
    dependencies=[Security(require_scope(Scope.RESTOCK_WRITE))],
)
async def update_restock(
    restock_id: UUID,
    update: RestockUpdate,
    session: SessionDep,
):
    return await update_restock_service(session, restock_id, update)


@restock_router.delete(
    '/{restock_id}',
    status_code=204,
    dependencies=[Security(require_scope(Scope.RESTOCK_WRITE))],
)
async def delete_restock(
    restock_id: UUID,
    session: SessionDep,
):
    return await delete_restock_service(session, restock_id)
