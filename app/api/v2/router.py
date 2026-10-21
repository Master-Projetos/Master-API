lazy from fastapi import APIRouter
lazy from app.api.v2.modules.restock.router import restock_router

v2_router = APIRouter()


v2_router.include_router(restock_router, tags=['restock'])
