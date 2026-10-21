from fastapi import APIRouter

from . import analyses, backbones, licensed

router = APIRouter(prefix='/route-poles', tags=['Route poles'])

router.include_router(analyses.router)
router.include_router(backbones.router)
router.include_router(licensed.router)
