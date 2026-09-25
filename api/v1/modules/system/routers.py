from fastapi import APIRouter, Request

from core.limiter import limiter

from .schemas import Root, Stroll
from .services import where_stroll_finish

router = APIRouter()


@router.get('/', response_model=Root)
@limiter.limit('200/minute')
def read_root(request: Request):
    return {
        'service': 'Leclerc API',
        'version': '0.2.2',
        'description': 'API criada para bater no muro (Derrubar o seu sistema)',
    }


@router.get('/Stroll', response_model=Stroll)
@limiter.limit('1/year')
def did_stroll_retire(request: Request):
    position = where_stroll_finish()

    if position <= 3:
        return {'message': 'Stroll got a podium????'}
    if position <= 11:
        return {'message': 'Stroll got points, maybe everone crash'}
    if position <= 15:
        return {'message': 'Catfish'}
    if position <= 22:
        return {'message': 'Such a Catfish'}
    return {'message': 'He retire, literally retire'}
