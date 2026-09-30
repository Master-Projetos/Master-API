import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.settings import get_settings
from app.modules.api_key.model import ApiKey, Scope
from app.modules.user.model import User, UserRole

oauth2_scheme = OAuth2PasswordBearer('api/v3/auth/token')
api_key_header = APIKeyHeader(name='X-API-Key', auto_error=False)
password_hasher = PasswordHash.recommended()

settings = get_settings()
DUMMY_PASSWORD_HASH = password_hasher.hash('dummy_password')

API_KEY_PREFIX = 'lk'
API_KEY_PARTS = 3
LAST_USED_UPDATE_INTERVAL = timedelta(minutes=5)


def get_password_hash(plain_password: str) -> str:
    return password_hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hasher.verify(plain_password, hashed_password)


async def authenticate_user_service(
    session: AsyncSession, email: str, password: str
):
    user = await session.scalar(
        select(User).where(User.email == email.lower().strip())
    )

    if not user:
        verify_password(password, DUMMY_PASSWORD_HASH)
        return None

    if not verify_password(password, user.hashed_password):
        return None

    return user


def create_access_token(user_id: UUID) -> str:
    now = datetime.now(tz=timezone.utc)
    token_payload = {
        'sub': str(user_id),
        'iat': now,
        'exp': now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(token_payload, settings.SECRET_KEY, algorithm='HS256')


async def get_current_user(
    session: AsyncSession = Depends(get_session),
    token: str = Depends(oauth2_scheme),
) -> User:
    invalid_token_exception = HTTPException(
        status_code=HTTPStatus.UNAUTHORIZED,
        detail='Could not validate credentials',
        headers={'WWW-Authenticate': 'Bearer'},
    )
    try:
        decoded_token = jwt.decode(
            token, settings.SECRET_KEY, algorithms=['HS256']
        )
        user_id = UUID(decoded_token['sub'])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise invalid_token_exception from None

    user = await session.scalar(select(User).where(User.id == user_id))
    if not user or not user.is_active:
        raise invalid_token_exception

    return user


async def get_current_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="You don't have permission to access this resource. ",
        )

    return current_user


def generate_api_key() -> tuple[str, str]:
    # Hex prefix never contains '_', so the key can be split safely
    prefix = secrets.token_hex(4)
    secret = secrets.token_urlsafe(32)
    return f'{API_KEY_PREFIX}_{prefix}_{secret}', prefix


def hash_api_key(raw_key: str) -> str:
    # SHA-256 is enough here: the key has 256 random bits, unlike a password
    return hashlib.sha256(raw_key.encode()).hexdigest()


@dataclass(frozen=True)
class ApiKeyPrincipal:
    user: User
    key_id: UUID
    scopes: frozenset[str]


async def get_api_key_principal(
    request: Request,
    session: AsyncSession = Depends(get_session),
    raw_key: str | None = Security(api_key_header),
) -> ApiKeyPrincipal:
    # Same response for every failure, so callers can't tell which check failed
    invalid_key_exception = HTTPException(
        status_code=HTTPStatus.UNAUTHORIZED,
        detail='Invalid API key',
        headers={'WWW-Authenticate': 'ApiKey'},
    )
    if not raw_key:
        raise invalid_key_exception

    # maxsplit=2 because the secret itself may contain '_'
    parts = raw_key.split('_', 2)
    if len(parts) != API_KEY_PARTS or parts[0] != API_KEY_PREFIX:
        raise invalid_key_exception

    row = (
        await session.execute(
            select(ApiKey, User)
            .join(User, ApiKey.user_id == User.id)
            .where(ApiKey.prefix == parts[1])
        )
    ).first()
    if row is None:
        raise invalid_key_exception

    api_key, user = row
    if not hmac.compare_digest(api_key.key_hash, hash_api_key(raw_key)):
        raise invalid_key_exception

    # Checked on every request: revoking, expiring or deactivating the
    # user takes effect immediately
    now = datetime.now(tz=timezone.utc)
    is_expired = api_key.expires_at is not None and api_key.expires_at <= now
    if api_key.revoked_at is not None or is_expired or not user.is_active:
        raise invalid_key_exception

    # Avoid a DB write on every request
    if (
        api_key.last_used_at is None
        or now - api_key.last_used_at > LAST_USED_UPDATE_INTERVAL
    ):
        api_key.last_used_at = now
        await session.commit()

    # Used by the rate limiter key_func
    request.state.client = f'key:{api_key.id}'

    return ApiKeyPrincipal(
        user=user, key_id=api_key.id, scopes=frozenset(api_key.scopes)
    )


def require_scope(scope: Scope):
    async def dependency(
        principal: ApiKeyPrincipal = Depends(get_api_key_principal),
    ) -> ApiKeyPrincipal:
        if scope not in principal.scopes:
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail='API key lacks the required scope',
            )
        return principal

    return dependency


SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentAdmin = Annotated[User, Depends(get_current_admin)]
