lazy from typing import List
lazy from uuid import UUID

lazy from fastapi import APIRouter, Security

lazy from app.api.v2.modules.poles.carriers.schemas import (
    CarriesValueCreate,
    CarriesValueGet,
    CarriesValueUpdate,
)
lazy from app.core.security import SessionDep, require_scope
lazy from app.modules.api_key.model import Scope
lazy from app.modules.poles.carriers.services import (
    create_carrier_values,
    delete_carrier_values,
    get_all_electric_carrier,
    get_electric_carrier_by_id,
    update_carrier_values,
)

carriers_router = APIRouter(
    dependencies=[Security(require_scope(Scope.POLES_READ))]
)


@carriers_router.get('/carriers', response_model=List[CarriesValueGet])
async def read_all_electric_carriers(session: SessionDep):
    return await get_all_electric_carrier(session)


@carriers_router.get(
    '/carriers/{carrier_id}', response_model=CarriesValueCreate
)
async def get_licensed_carrier_by_id(carrier_id: UUID, session: SessionDep):
    return await get_electric_carrier_by_id(session, carrier_id)


@carriers_router.post(
    '/carriers',
    response_model=CarriesValueGet,
    status_code=201,
    dependencies=[Security(require_scope(Scope.ROUTE_POLES_WRITE))],
)
async def create_electric_carrier(
    request_body: CarriesValueCreate,
    session: SessionDep,
):
    return await create_carrier_values(session, request_body)


@carriers_router.patch(
    '/carriers/{carrier_id}',
    response_model=CarriesValueGet,
    dependencies=[Security(require_scope(Scope.ROUTE_POLES_WRITE))],
)
async def update_electric_carrier(
    carrier_id: UUID,
    request_body: CarriesValueUpdate,
    session: SessionDep,
):
    return await update_carrier_values(session, carrier_id, request_body)


@carriers_router.delete(
    '/carriers/{carrier_id}',
    status_code=204,
    dependencies=[Security(require_scope(Scope.ROUTE_POLES_WRITE))],
)
async def delete_electric_carrier(carrier_id: UUID, session: SessionDep):
    return await delete_carrier_values(session, carrier_id)
