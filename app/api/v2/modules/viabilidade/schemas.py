from pydantic import BaseModel


class CityClients(BaseModel):
    city: str
    clients: int


class TechnologyCount(BaseModel):
    technology: str
    total: int
