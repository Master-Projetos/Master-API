import re
from typing import Annotated

from fastapi import APIRouter, Path, Request
from fastapi.concurrency import run_in_threadpool

from app.core.limiter import limiter
from app.modules.route_poles.analysis.kmz import KmzKind
from app.modules.route_poles.analysis.pipeline import run_city_poles

from .dependencies import analysis_errors, read_scope
from .presenters import KMZ_FILE_PREFIX, kmz_download

router = APIRouter(prefix='/cities')

IBGE_CODE = re.compile(r'\d{7}')

CityRef = Annotated[
    str,
    Path(
        max_length=100,
        description='City name (accents and case ignored) or IBGE code, '
        'e.g. Divinópolis or 3122306. Use the IBGE code when two cities '
        'share the name',
    ),
]


# With the API key, unlike the stored KMZ: a city name is easy to guess and
# each download reads the whole pole bases
@router.get('/{city_ref}/poles.kmz', dependencies=[read_scope])
@limiter.limit('5/minute')
async def download_city_poles_kmz(request: Request, city_ref: CityRef):
    """Every pole of the pole bases inside the IBGE boundary of the city."""
    ref = city_ref.strip()
    name, code = (None, ref) if IBGE_CODE.fullmatch(ref) else (ref, None)
    with analysis_errors():
        city, content = await run_in_threadpool(run_city_poles, name, code)
    prefix = KMZ_FILE_PREFIX[KmzKind.ALL_POLES]
    return kmz_download(f'{prefix}_{city.code}_{city.name}', content)
