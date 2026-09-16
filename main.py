from fastapi import FastAPI
from core.settings import get_settings
from v1.router import v1_router


settings = get_settings()

app = FastAPI(
    title='Leclerc API',
    version= settings.API_VERSION,
    openapi_url='/openapi.json'
    if settings.DEBUG else None,
)

app.include_router(v1_router, prefix="/api/v1")