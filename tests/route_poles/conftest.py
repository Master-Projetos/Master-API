import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.modules.route_poles import model  # noqa: F401  registers the tables
from app.modules.route_poles.analysis import city_poles as city_poles_module
from app.modules.route_poles.analysis import pipeline
from app.modules.route_poles.analysis.city import Area, City
from app.modules.route_poles.schemas import AnalysisOptions, RouteUploadOptions
from tests.route_poles import scenarios as sc


def route_tables():
    return [
        table
        for name, table in Base.metadata.tables.items()
        if name.startswith(('route_', 'backbone', 'licensed_'))
    ]


ALL_KMZ = {'export_all': True, 'overlap_kmz': True, 'overlap_split_kmz': True}


def make_city(code_name, box) -> City:
    return City(*code_name, Area([[sc.ring(box)]]))


@pytest.fixture
def city_a():
    return make_city(sc.CITY_A, sc.CITY_A_BOX)


@pytest.fixture
def city_b():
    return make_city(sc.CITY_B, sc.CITY_B_BOX)


@pytest.fixture
def pole_bases(monkeypatch):
    monkeypatch.setattr(city_poles_module, 'local_bases', sc.fake_local_bases)
    monkeypatch.setattr(city_poles_module, 'read_poles', sc.fake_read_poles)


@pytest.fixture
def routes_in_a_and_b(monkeypatch, pole_bases, city_a, city_b):
    monkeypatch.setattr(pipeline, 'find_city', lambda *_: city_a)
    monkeypatch.setattr(pipeline, 'find_cities', lambda *_: [city_a, city_b])


@pytest.fixture
def analysis_data(routes_in_a_and_b):
    return pipeline.run_analysis(
        sc.routes_kmz(), 'backbone_bh.kmz', RouteUploadOptions(**ALL_KMZ)
    )


@pytest.fixture
def plain_analysis_data(routes_in_a_and_b):
    return pipeline.run_analysis(
        sc.routes_kmz(), 'plain.kmz', RouteUploadOptions()
    )


@pytest.fixture
def backbone_data(routes_in_a_and_b):
    return pipeline.run_backbone(
        sc.routes_kmz(), 'backbone_bh.kmz', AnalysisOptions(**ALL_KMZ)
    )


@pytest.fixture
def plain_backbone_data(routes_in_a_and_b):
    return pipeline.run_backbone(
        sc.routes_kmz(), 'backbone_plain.kmz', AnalysisOptions()
    )


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.fixture
async def session_factory():
    engine = create_async_engine('sqlite+aiosqlite://', poolclass=StaticPool)

    @event.listens_for(engine.sync_engine, 'connect')
    def enable_foreign_keys(connection, _):
        # The ON DELETE CASCADE of the rows is what removes the children
        connection.execute('PRAGMA foreign_keys=ON')

    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync: Base.metadata.create_all(sync, tables=route_tables())
        )
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def session(session_factory):
    async with session_factory() as session:
        yield session
