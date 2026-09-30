from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import ARRAY, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Scope(StrEnum):
    STOCK_READ = 'stock:read'
    B2B_READ = 'b2b:read'
    GEOGRID_READ = 'geogrid:read'


class ApiKey(Base):
    __tablename__ = 'api_keys'

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey('users.id', ondelete='CASCADE'), index=True
    )
    name: Mapped[str] = mapped_column(String(100))

    # Public part of the key, used to look up the row
    prefix: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    # SHA-256 hex digest of the full key; the plain key is never stored
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)

    scopes: Mapped[list[str]] = mapped_column(ARRAY(String(50)))

    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
