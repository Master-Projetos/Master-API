from fastapi import APIRouter

from app.api.v6.stock.router import router as stock_router

v6_router = APIRouter()

v6_router.include_router(stock_router)
