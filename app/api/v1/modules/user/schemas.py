from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.modules.user.model import UserRole


class UserCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            'examples': [
                {
                    'username': 'joao.silva',
                    'email': 'joao.silva@empresa.com',
                    'password': 'troque-esta-senha',
                    'role': UserRole.USER.value,
                }
            ]
        }
    )

    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.USER


class UserUpdate(BaseModel):
    # Every field is optional: delete the ones that should not change
    model_config = ConfigDict(
        json_schema_extra={
            'examples': [
                {
                    'username': 'joao.silva',
                    'email': 'joao.silva@empresa.com',
                    'password': 'troque-esta-senha',
                }
            ]
        }
    )

    username: str | None = Field(default=None, min_length=3, max_length=50)
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class AdminUserUpdate(UserUpdate):
    # Overrides the inherited example to also show the admin-only fields
    model_config = ConfigDict(
        json_schema_extra={
            'examples': [
                {
                    'username': 'joao.silva',
                    'email': 'joao.silva@empresa.com',
                    'password': 'troque-esta-senha',
                    'role': UserRole.USER.value,
                    'is_active': True,
                }
            ]
        }
    )

    role: UserRole | None = None
    is_active: bool | None = None


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    email: EmailStr
    role: UserRole
    is_active: bool
