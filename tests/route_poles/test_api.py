import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.exc import IntegrityError

from app.api.v8.route_poles import backbones, dependencies
from app.api.v8.router import v8_router
from app.core.database import get_session
from app.core.limiter import limiter
from app.modules.route_poles.analysis import pipeline
from app.modules.route_poles.analysis.errors import SourceError
from tests.route_poles import scenarios as sc

pytestmark = pytest.mark.anyio

BASE_URL = 'https://testserver/api/v8/route-poles'
KMZ_TYPE = 'application/vnd.google-earth.kmz'
MAX_FILENAME = 300
CITIES = 2
EDITED = 99


@pytest.fixture
async def client(session_factory, monkeypatch):
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(v8_router, prefix='/api/v8')

    async def test_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    app.dependency_overrides[dependencies.read_scope.dependency] = lambda: None
    app.dependency_overrides[dependencies.write_scope.dependency] = lambda: (
        None
    )
    monkeypatch.setattr(limiter, 'enabled', False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url=BASE_URL
    ) as client:
        yield client


def upload(content=None, filename='backbone_bh.kmz'):
    return {'file': (filename, content or sc.routes_kmz(), KMZ_TYPE)}


def raising(error):
    def fail(*_, **__):
        raise error

    return fail


async def test_backbone_lifecycle(client, routes_in_a_and_b):
    response = await client.post(
        '/backbones', files=upload(), data={'overlap_split_kmz': 'true'}
    )

    assert response.status_code == httpx.codes.CREATED
    created = response.json()
    assert created['code'].endswith('_backbone_bh')
    assert created['routes_file'] == 'backbone_bh.kmz'
    assert created['cities_count'] == len(created['cities']) == CITIES
    assert created['route_length_m'] == sum(
        city['route_length_m'] for city in created['cities']
    )
    city = created['cities'][0]
    assert city['poles_kmz_url'].startswith(f'{BASE_URL}/backbones/cities/')
    assert city['with_overlap_kmz_url']
    assert city['without_overlap_kmz_url']
    assert city['all_poles_kmz_url'] is None
    assert city['overlap_kmz_url'] is None

    listed = (await client.get('/backbones')).json()
    assert [b['id'] for b in listed] == [created['id']]
    by_city = await client.get('/backbones', params={'ibge_code': '3132404'})
    assert len(by_city.json()) == 1
    nothing = await client.get('/backbones', params={'city': 'atlantis'})
    assert nothing.json() == []

    detail = (await client.get(f'/backbones/{created["code"]}')).json()
    by_id = (await client.get(f'/backbones/{created["id"]}')).json()
    assert detail == by_id
    assert all(c['cable_types'] and c['cables'] for c in detail['cities'])

    kmz = await client.get(city['poles_kmz_url'])
    assert kmz.status_code == httpx.codes.OK
    assert kmz.headers['content-type'] == KMZ_TYPE
    assert (
        "filename*=UTF-8''postes_utilizados_"
        in (kmz.headers['content-disposition'])
    )
    assert kmz.content[:2] == b'PK'
    missing = await client.get(
        city['poles_kmz_url'].replace('poles', 'overlap')
    )
    assert missing.status_code == httpx.codes.NOT_FOUND

    deleted = await client.delete(f'/backbones/{created["code"]}')
    assert deleted.status_code == httpx.codes.NO_CONTENT
    assert (
        await client.get(f'/backbones/{created["id"]}')
    ).status_code == httpx.codes.NOT_FOUND
    assert (
        await client.delete(f'/backbones/{created["id"]}')
    ).status_code == httpx.codes.NOT_FOUND
    assert (
        await client.get(city['poles_kmz_url'])
    ).status_code == httpx.codes.NOT_FOUND


async def test_uploading_a_backbone_again_replaces_it(
    client, routes_in_a_and_b
):
    first = (await client.post('/backbones', files=upload())).json()
    second = (await client.post('/backbones', files=upload())).json()

    assert first['code'] == second['code']
    assert first['id'] != second['id']
    assert len((await client.get('/backbones')).json()) == 1


async def test_links_keep_the_scheme_of_the_client(client, routes_in_a_and_b):
    response = await client.post(
        '/backbones', files=upload(), headers={'x-forwarded-proto': 'http'}
    )

    url = response.json()['cities'][0]['poles_kmz_url']
    assert url.startswith('http://testserver/')


@pytest.mark.parametrize('radius', ['0', '-5', '1000', 'abc'])
async def test_invalid_form_options_are_422(client, routes_in_a_and_b, radius):
    response = await client.post(
        '/backbones', files=upload(), data={'radius_m': radius}
    )
    assert response.status_code == httpx.codes.UNPROCESSABLE_ENTITY


async def test_a_file_that_is_not_a_kml_is_422(client, routes_in_a_and_b):
    response = await client.post('/backbones', files=upload(b'not a kml'))

    assert response.status_code == httpx.codes.UNPROCESSABLE_ENTITY
    assert 'not a valid KML' in response.json()['detail']


async def test_a_file_name_that_does_not_fit_is_422_without_the_input(
    client, routes_in_a_and_b
):
    name = 'a' * MAX_FILENAME + '.kmz'
    response = await client.post('/backbones', files=upload(filename=name))

    assert response.status_code == httpx.codes.UNPROCESSABLE_ENTITY
    assert 'input' not in response.text


async def test_ibge_down_is_502(client, monkeypatch, routes_in_a_and_b):
    monkeypatch.setattr(
        pipeline, 'find_cities', raising(SourceError('IBGE is down'))
    )
    response = await client.post('/backbones', files=upload())

    assert response.status_code == httpx.codes.BAD_GATEWAY
    assert response.json()['detail'] == 'IBGE is down'


async def test_pole_base_download_failure_is_502(
    client, monkeypatch, routes_in_a_and_b
):
    monkeypatch.setattr(
        pipeline, 'find_cities', raising(OSError('connection reset'))
    )
    response = await client.post('/backbones', files=upload())

    assert response.status_code == httpx.codes.BAD_GATEWAY
    assert 'Could not download' in response.json()['detail']


async def test_a_file_over_the_limit_is_413(client, monkeypatch):
    monkeypatch.setattr(dependencies, 'MAX_UPLOAD_BYTES', 10)
    response = await client.post('/backbones', files=upload())
    assert response.status_code == httpx.codes.REQUEST_ENTITY_TOO_LARGE


async def test_a_concurrent_save_is_409(
    client, monkeypatch, routes_in_a_and_b
):
    error = IntegrityError('insert', {}, Exception('duplicate'))
    monkeypatch.setattr(backbones, 'save_backbone', raising(error))
    response = await client.post('/backbones', files=upload())

    assert response.status_code == httpx.codes.CONFLICT
    assert 'being saved' in response.json()['detail']


async def test_analysis_lifecycle(client, routes_in_a_and_b):
    response = await client.post(
        '/analyses',
        files=upload(),
        # What Swagger UI sends for optional fields left alone
        data={'overlap_split_kmz': 'true', 'city': 'string', 'ibge_code': ''},
    )

    assert response.status_code == httpx.codes.CREATED
    created = response.json()
    assert (
        created['length_with_overlap_m'] > created['length_without_overlap_m']
    )
    assert created['with_overlap_kmz_url']
    assert created['all_poles_kmz_url'] is None

    listed = (await client.get('/analyses')).json()
    assert [a['id'] for a in listed] == [created['id']]
    assert listed[0]['ibge_code'] == '3122306'
    assert (
        await client.get('/analyses', params={'ibge_code': '1'})
    ).json() == []

    detail = (await client.get(f'/analyses/{created["code"]}')).json()
    assert detail['id'] == created['id']
    assert detail['cable_types']
    assert detail['cables']
    assert 'cities' not in detail

    kmz = await client.get(created['with_overlap_kmz_url'])
    assert kmz.status_code == httpx.codes.OK
    assert 'cabos_com_sobreposicao_' in kmz.headers['content-disposition']

    deleted = await client.delete(f'/analyses/{created["code"]}')
    assert deleted.status_code == httpx.codes.NO_CONTENT
    assert (
        await client.get(f'/analyses/{created["id"]}')
    ).status_code == httpx.codes.NOT_FOUND


async def test_analysis_csvs(client, routes_in_a_and_b):
    created = (await client.post('/analyses', files=upload())).json()

    summary = await client.get('/csv/summary.csv')
    assert summary.headers['content-type'] == 'text/csv; charset=utf-8'
    header, row = summary.text.splitlines()
    assert header.startswith('ID análise,Data,Município')
    assert row.startswith(created['code'])
    assert created['poles_kmz_url'] in row

    cable_types = await client.get('/csv/cable-types.csv')
    assert len(cable_types.text.splitlines()) > 1
    cables = await client.get(
        '/csv/cables.csv', params={'ibge_code': '3122306'}
    )
    assert len(cables.text.splitlines()) > 1
    none = await client.get('/csv/cables.csv', params={'ibge_code': '1'})
    assert len(none.text.splitlines()) == 1
    unknown = await client.get('/csv/other.csv')
    assert unknown.status_code == httpx.codes.UNPROCESSABLE_ENTITY


async def test_unknown_analyses_are_404(client):
    assert (
        await client.get('/analyses/missing')
    ).status_code == httpx.codes.NOT_FOUND
    assert (
        await client.delete('/analyses/missing')
    ).status_code == httpx.codes.NOT_FOUND


@pytest.mark.parametrize(
    'path',
    [
        '/analyses/upload',
        '/analyses/upload-multi',
        '/analyses/upload-backbone',
    ],
)
async def test_the_old_upload_routes_are_gone(client, path):
    response = await client.post(path, files=upload())
    assert response.status_code in {404, 405}
