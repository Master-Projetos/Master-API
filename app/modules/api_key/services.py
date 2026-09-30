from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_api_key, hash_api_key
from app.modules.api_key.model import ApiKey, Scope

MAX_ACTIVE_KEYS_PER_USER = 10


async def create_api_key_service(
    session: AsyncSession,
    user_id: UUID,
    name: str,
    scopes: set[Scope],
    expires_in_days: int | None,
) -> tuple[ApiKey, str]:
    now = datetime.now(tz=timezone.utc)

    active_keys_count = await session.scalar(
        select(func.count())
        .select_from(ApiKey)
        .where(
            ApiKey.user_id == user_id,
            ApiKey.revoked_at.is_(None),
            or_(ApiKey.expires_at.is_(None), ApiKey.expires_at > now),
        )
    )
    if active_keys_count >= MAX_ACTIVE_KEYS_PER_USER:
        raise ValueError('Active API key limit reached.')

    raw_key, prefix = generate_api_key()
    api_key = ApiKey(
        user_id=user_id,
        name=name,
        prefix=prefix,
        key_hash=hash_api_key(raw_key),
        scopes=sorted(scopes),
        expires_at=(
            now + timedelta(days=expires_in_days) if expires_in_days else None
        ),
    )
    session.add(api_key)
    await session.commit()
    await session.refresh(api_key)

    # The plain key leaves this function once and is never stored
    return api_key, raw_key


async def list_api_keys_service(
    session: AsyncSession, user_id: UUID | None
) -> list[ApiKey]:
    query = select(ApiKey).order_by(ApiKey.created_at.desc())
    # user_id=None lists every key and is only for admins
    if user_id is not None:
        query = query.where(ApiKey.user_id == user_id)

    api_keys = await session.scalars(query)
    return list(api_keys.all())


async def revoke_api_key_service(
    session: AsyncSession, key_id: UUID, owner_id: UUID | None
) -> bool:
    query = select(ApiKey).where(
        ApiKey.id == key_id, ApiKey.revoked_at.is_(None)
    )
    # owner_id=None is only for admins; regular users must always pass it
    if owner_id is not None:
        query = query.where(ApiKey.user_id == owner_id)

    api_key = await session.scalar(query)
    if not api_key:
        return False

    api_key.revoked_at = datetime.now(tz=timezone.utc)
    await session.commit()
    return True
