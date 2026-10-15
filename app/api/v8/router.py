from fastapi import APIRouter

from app.api.v8.route_poles.router import router as route_poles_router

v8_router = APIRouter()

v8_router.include_router(route_poles_router)
