from pydantic import BaseModel, Field


class PoleData(BaseModel):
    ibge_code: int = Field(alias='CODIGO IBGE')
    license_poles: int = Field(alias='POSTES LICENCIADOS')
    value: float = Field(alias='VALOR')


PolesByCity = dict[str, PoleData]
PolesByUtility = dict[str, PolesByCity]
