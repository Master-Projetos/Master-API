from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def get_rate_limit_key(request: Request) -> str:
    # Authenticated requests are limited per API key, the rest per IP
    client = getattr(request.state, 'client', None)
    return client or get_remote_address(request)


limiter = Limiter(key_func=get_rate_limit_key)
