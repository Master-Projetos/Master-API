lazy from typing import List
lazy from uuid import UUID

lazy from fastapi import APIRouter, Security

lazy from app.api.v2.modules.poles.licensed_poles.schemas import (
    LicensedPolesCreate,
    LicensedPolesGet,
    LicensedPolesUpdate,
)
lazy from app.core.security import SessionDep, require_scope
lazy from app.modules.api_key.model import Scope
lazy from app.modules.poles.licensed_poles.services import (
    create_licensed_poles_service,
    delete_licensed_poles,
    get_licensed_poles,
    get_licensed_poles_by_id,
    update_licensed_poles,
)

licensed_poles_router = APIRouter(
    dependencies=[Security(require_scope(Scope.POLES_READ))]
)


@licensed_poles_router.get('/poles', response_model=List[LicensedPolesGet])
async def read_all_licensed_poles(session: SessionDep):
    return await get_licensed_poles(session)


@licensed_poles_router.get(
    '/poles/{licensed_pole_id}', response_model=LicensedPolesGet
)
async def get_licensed_pole(licensed_pole_id: UUID, session: SessionDep):
    return await get_licensed_poles_by_id(session, licensed_pole_id)


@licensed_poles_router.post(
    '/poles',
    response_model=LicensedPolesGet,
    status_code=201,
    dependencies=[Security(require_scope(Scope.ROUTE_POLES_WRITE))],
)
async def create_licensed_pole(
    request_body: LicensedPolesCreate,
    session: SessionDep,
):
    return await create_licensed_poles_service(session, request_body)


@licensed_poles_router.patch(
    '/poles/{licensed_pole_id}',
    response_model=LicensedPolesGet,
    dependencies=[Security(require_scope(Scope.ROUTE_POLES_WRITE))],
)
async def update_licensed_pole(
    licensed_pole_id: UUID,
    request_body: LicensedPolesUpdate,
    session: SessionDep,
):
    return await update_licensed_poles(session, licensed_pole_id, request_body)


@licensed_poles_router.delete(
    '/poles/{licensed_pole_id}',
    status_code=204,
    dependencies=[Security(require_scope(Scope.ROUTE_POLES_WRITE))],
)
async def delete_licensed_pole(licensed_pole_id: UUID, session: SessionDep):
    return await delete_licensed_poles(session, licensed_pole_id)
