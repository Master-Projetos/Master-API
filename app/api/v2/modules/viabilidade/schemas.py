from pydantic import BaseModel


class Revenue(BaseModel):
    clients: int
    revenue: float
    average_ticket: float


class ClientsCount(Revenue):
    wireless: int
    non_wireless: int


class CityClients(ClientsCount):
    city: str
    neighborhoods: dict[str, ClientsCount]


class WirelessCityClients(Revenue):
    city: str
    neighborhoods: dict[str, Revenue]


class TechnologyCount(BaseModel):
    technology: str
    total: int
