from fastapi import APIRouter

from .modules.reports.routers import router as report_router
from .modules.system.routers import router as system_router

v1_router = APIRouter()

v1_router.include_router(report_router)
v1_router.include_router(system_router)
