from fastapi import APIRouter
from app.modules.geogrid.v2.viability.router import viability_router

geogrid_router = APIRouter()


geogrid_router.include_router(
    viability_router, prefix='/viability', tags=['geogrid']
)
