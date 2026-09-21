from pydantic import BaseModel, ConfigDict, Field


class ReportSchema(BaseModel):
    status: str
    relatory: str


class Estatisticas(BaseModel):
    equipamentos: int = Field(alias='Equipamentos')
    portas: int = Field(alias='Portas')
    portas_ocupadas: int = Field(alias='Portas ocupadas')
    portas_livres: int = Field(alias='Portas livres')
    portas_bloqueadas: int = Field(alias='Portas bloqueadas')
    portas_atendimento_cliente: int = Field(alias='Portas atendimento cliente')

    model_config = ConfigDict(populate_by_name=True)


class RegistroRecipiente(BaseModel):
    sigla: str = Field(alias='Sigla')
    latitude: str = Field(alias='Latitude')
    longitude: str = Field(alias='Longitude')
    quantidade_equip: float = Field(alias='Quantidade equip.')
    quantidade_portas: float = Field(alias='Quantidade portas')
    portas_ocupadas: float = Field(alias='Portas ocupadas')
    portas_livres: float = Field(alias='Portas livres')
    portas_bloqueadas: float = Field(alias='Portas bloqueadas')
    portas_atendimento_cliente: float = Field(
        alias='Portas atendimento cliente'
    )

    model_config = ConfigDict(populate_by_name=True)


RegistrosPorRegiao = dict[str, dict[str, list[RegistroRecipiente]]]


class Viabily(BaseModel):
    estatisticas: Estatisticas
    estatisticas_regiao: dict[str, Estatisticas]
    ctos: RegistrosPorRegiao
    ceos: RegistrosPorRegiao
