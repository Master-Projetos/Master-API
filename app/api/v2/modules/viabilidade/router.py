from typing import List

lazy from fastapi import APIRouter, Security

lazy from app.api.v2.modules.viabilidade.schemas import (
    CityClients,
    TechnologyCount,
    WirelessCityClients,
)
lazy from app.core.security import require_scope
lazy from app.modules.api_key.model import Scope
lazy from app.modules.viabilidade.services import (
    get_clients_by_city,
    get_clients_by_city_name,
    get_technologies,
    get_wireless_clients_by_city,
    get_wireless_clients_by_city_name,
)

viabilidade_router = APIRouter(
    dependencies=[Security(require_scope(Scope.VIABILIDADE_READ))]
)


@viabilidade_router.get('/cities', response_model=List[CityClients])
def read_clients_by_city():
    return get_clients_by_city()


@viabilidade_router.get('/cities/{city}', response_model=CityClients)
def read_clients_by_city_name(city: str):
    return get_clients_by_city_name(city)


@viabilidade_router.get(
    '/wireless/cities', response_model=List[WirelessCityClients]
)
def read_wireless_clients_by_city():
    return get_wireless_clients_by_city()


@viabilidade_router.get(
    '/wireless/cities/{city}', response_model=WirelessCityClients
)
def read_wireless_clients_by_city_name(city: str):
    return get_wireless_clients_by_city_name(city)


@viabilidade_router.get('/technologies', response_model=List[TechnologyCount])
def read_technologies():
    return get_technologies()
