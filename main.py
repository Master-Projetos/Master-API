from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from core.settings import get_settings
from core.logger import setup_logging
from core.limiter import limiter
from api.v1.router import v1_router
from api.v2.router import v2_router

setup_logging()

settings = get_settings()

app = FastAPI(
    title='Leclerc API',
    version=settings.API_VERSION,
    openapi_url='/openapi.json' if settings.DEBUG else None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(v1_router, prefix='/api/v1')
app.include_router(v2_router, prefix='/api/v2')
