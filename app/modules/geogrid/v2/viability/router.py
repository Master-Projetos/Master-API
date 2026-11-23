lazy from fastapi import APIRouter

from app.core.security import SessionDep
from app.modules.geogrid.v2.viability.services import (
    sync_viability_record,
    fetch_viability_record,
)

viability_router = APIRouter()


@viability_router.get('/get')
async def get_viability_record(session: SessionDep):
    return {'records': await fetch_viability_record(session)}


@viability_router.post('/sync')
async def sync_viability(session: SessionDep):
    return {'inserted': await sync_viability_record(session)}
