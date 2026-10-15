from fastapi import APIRouter

from app.api.v7.poles.router import router as poles_router

v7_router = APIRouter()

v7_router.include_router(poles_router)
