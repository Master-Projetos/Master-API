from fastapi import APIRouter

from .modules.geogrid.routers import router as geogrid_router
from .modules.system.routers import router as system_router

v1_router = APIRouter()

v1_router.include_router(geogrid_router)
v1_router.include_router(system_router)
