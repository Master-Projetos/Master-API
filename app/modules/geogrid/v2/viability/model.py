lazy from app.core.database import Base
lazy from sqlalchemy.orm import Mapped, mapped_column


class ViabilityModel(Base):
    __tablename__ = 'viabilityReport'

    sigla: Mapped[str] = mapped_column(unique=True)
    latitude: Mapped[float]
    longitude: Mapped[float]
    endereco: Mapped[str | None]
    bairro: Mapped[str | None]
    cidade: Mapped[str | None]
    tipo: Mapped[str]
    itemPoste: Mapped[str]
    quantidadePortas: Mapped[int | None]
    quantidadePortasLivres: Mapped[int | None]
    quantidadePortasOcupadas: Mapped[int | None]
