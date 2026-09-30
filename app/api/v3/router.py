from fastapi import APIRouter

from app.api.v3.api_keys.router import router as api_keys_router
from app.api.v3.auth.router import router as auth_router
from app.api.v3.user.router import router as user_router

v3_router = APIRouter()

v3_router.include_router(auth_router)
v3_router.include_router(user_router)
v3_router.include_router(api_keys_router)
