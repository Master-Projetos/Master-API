from datetime import date

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
    tipo: str = Field('', alias='Tipo')
    latitude: str = Field(alias='Latitude')
    longitude: str = Field(alias='Longitude')
    bairro: str = Field('', alias='Bairro')
    cep: str = Field('', alias='CEP')
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
RegistrosPorTipo = dict[str, RegistrosPorRegiao]


class Viabily(BaseModel):
    estatisticas: Estatisticas
    estatisticas_regiao: dict[str, Estatisticas]
    estatisticas_tipo: dict[str, Estatisticas]
    ctos: RegistrosPorTipo
    ceos: RegistrosPorTipo


class CriticalCto(BaseModel):
    # Geogrid
    sigla: str
    cidade: str
    regiao: str
    bairro: str
    tipo: str
    quantidade_portas: int
    portas_ocupadas: int
    portas_livres: int
    portas_bloqueadas: int
    # True when the sigla repeats in Geogrid and the city was also compared
    casou_por_cidade: bool
    # Attendants' sheet
    nomenclaturas: list[str]
    cidades_planilha: list[str]
    abas: list[str]
    atendentes: list[str]
    tecnicos: list[str]
    ultima_data: date | None
    portas_planilha: int
    portas_com_cliente: int
    portas_livres_planilha: int
    portas_nao_checadas: int


class CriticalCtosResponse(BaseModel):
    max_livres: int
    total_criticas: int
    total_encontradas: int
    ctos: list[CriticalCto]
