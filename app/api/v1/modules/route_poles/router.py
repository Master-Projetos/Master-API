from fastapi import APIRouter

lazy from app.api.v1.modules.route_poles import (
    analyses,
    backbones,
    cities,
    licensed,
)

router = APIRouter(prefix='/route-poles', tags=['Route poles'])

router.include_router(analyses.router)
router.include_router(backbones.router)
router.include_router(licensed.router)
router.include_router(cities.router)
