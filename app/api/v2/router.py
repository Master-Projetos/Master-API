lazy from fastapi import APIRouter

lazy from app.api.v2.modules.licensed_poles.router import licensed_poles_router
lazy from app.api.v2.modules.restock.router import restock_router

v2_router = APIRouter()


v2_router.include_router(restock_router, prefix='/restock', tags=['restock'])
v2_router.include_router(
    licensed_poles_router, prefix='/licensed-poles', tags=['licensed_poles']
)
