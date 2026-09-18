from pydantic import BaseModel


class Root(BaseModel):
    service: str
    version: str
    description: str


class Stroll(BaseModel):
    message: str
