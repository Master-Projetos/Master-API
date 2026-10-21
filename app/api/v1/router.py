from fastapi import APIRouter

from app.api.v1.modules.geogrid.routers import router as geogrid_router
from app.api.v1.modules.system.routers import router as system_router
from app.api.v1.modules.B2B.routers import router as b2b_router
from app.api.v1.modules.stock.routers import router as stock_router
from app.api.v1.modules.api_keys.router import router as api_keys_router
from app.api.v1.modules.auth.router import router as auth_router
from app.api.v1.modules.user.router import router as user_router
from app.api.v1.modules.swap.router import router as swap_router
from app.api.v1.modules.poles.router import router as poles_router
from app.api.v1.modules.route_poles.router import router as route_poles_router


v1_router = APIRouter()

v1_router.include_router(system_router)
v1_router.include_router(b2b_router)
v1_router.include_router(stock_router)
v1_router.include_router(auth_router)
v1_router.include_router(user_router)
v1_router.include_router(api_keys_router)
v1_router.include_router(swap_router)
v1_router.include_router(poles_router)
v1_router.include_router(route_poles_router)
# Last: its POST /{relatory} catch-all would swallow /api-keys, /users, etc.
v1_router.include_router(geogrid_router)
