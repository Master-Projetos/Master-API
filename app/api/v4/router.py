from fastapi import APIRouter

from app.api.v4.swap.router import router as swap_router

v4_router = APIRouter()

v4_router.include_router(swap_router)
