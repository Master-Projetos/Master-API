import sys
from fastapi import APIRouter, Request

from app.core.limiter import limiter

from app.api.v1.modules.system.schemas import Root
router = APIRouter()


@router.get('/', response_model=Root)
@limiter.limit('200/minute')
def read_root(request: Request):
    return {
        'service': 'Leclerc API',
        'version': '0.2.2',
        'description': 'API criada para bater no muro (Derrubar o seu sistema)',
        'python_version': sys.version,
    }

