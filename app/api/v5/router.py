from fastapi import APIRouter

from app.api.v5.swap.router import router as swap_router

v5_router = APIRouter()

v5_router.include_router(swap_router)
