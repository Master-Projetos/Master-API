from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address


def get_rate_limit_key(request: Request) -> str:
    # Authenticated requests are limited per API key, the rest per IP
    client = getattr(request.state, 'client', None)
    return client or get_remote_address(request)


async def rate_limit_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={'detail': 'Too Many Requests. Try again later.'},
        headers={'Retry-After': '5'},
    )


limiter = Limiter(key_func=get_rate_limit_key)
