from enum import StrEnum
from sqlalchemy import Enum, String, true
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class UserRole(StrEnum):
    ADMIN = 'admin'
    USER = 'user'


class User(Base):
    __tablename__ = 'users'

    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    hashed_password: Mapped[str] = mapped_column(String(255))

    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            values_callable=lambda role_enum: [
                role.value for role in role_enum
            ],
        ),
        default=UserRole.USER,
        server_default=UserRole.USER.value,
    )

    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
