from fastapi import APIRouter, Request
from core.limiter import limiter

router = APIRouter()

@router.get("/")
@limiter.limit("200/minute")
def read_root(request: Request):
    return {
        "service" : "Leclerc API",
        "version" : "0.2.1",
        "description": "API criada para bater no muro"
    }