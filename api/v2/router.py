from fastapi import APIRouter

from .modules.B2B.routers import router as b2b_router
from .modules.stock.routers import router as stock_router

v2_router = APIRouter()

v2_router.include_router(b2b_router)
v2_router.include_router(stock_router)
