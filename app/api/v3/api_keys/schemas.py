from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.api_key.model import Scope


class ApiKeyCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            'examples': [
                {
                    'name': 'exemple',
                    'scopes': [scope.value for scope in Scope],
                    'expires_in_days': 90,
                }
            ]
        }
    )

    name: str = Field(min_length=1, max_length=100)
    scopes: set[Scope] = Field(min_length=1)
    expires_in_days: int | None = Field(default=90, ge=1, le=365)


class ApiKeyPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    name: str
    prefix: str
    scopes: list[Scope]
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    last_used_at: datetime | None


class ApiKeyCreated(ApiKeyPublic):
    # Only returned once, on creation
    key: str
