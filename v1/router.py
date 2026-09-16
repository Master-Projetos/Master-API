from fastapi import APIRouter
from .modules.reports.routers import router as report_router

v1_router = APIRouter()

v1_router.include_router(report_router)