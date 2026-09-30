from datetime import datetime
from collections.abc import AsyncGenerator
from sqlalchemy import func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
from uuid import UUID, uuid4
from app.core.settings import get_settings


settings = get_settings()

engine = create_async_engine(
    url=settings.DATABASE_URL, echo=settings.DEBUG, pool_pre_ping=True
)

async_session = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


class Base(DeclarativeBase):
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
