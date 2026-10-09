from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.v1.router import v1_router
from app.api.v2.router import v2_router
from app.api.v3.router import v3_router
from app.api.v4.router import v4_router
from app.api.v5.router import v5_router
from app.api.v6.router import v6_router

from app.core.limiter import limiter
from app.core.logger import setup_logging
from app.core.settings import get_settings

setup_logging()

settings = get_settings()

app = FastAPI(
    title='Leclerc API',
    version=settings.API_VERSION,
    description="Batendo no seu sistema",
    openapi_url='/openapi.json' if settings.DEBUG else None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(v1_router, prefix='/api/v1')
app.include_router(v2_router, prefix='/api/v2')
app.include_router(v3_router, prefix='/api/v3')
app.include_router(v4_router, prefix='/api/v4')
app.include_router(v5_router, prefix='/api/v5')
app.include_router(v6_router, prefix='/api/v6')
