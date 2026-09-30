from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.modules.user.model import User, UserRole
from app.api.v3.user.schemas import AdminUserUpdate, UserCreate, UserUpdate


async def get_users_service(
    session: AsyncSession, offset: int = 0, limit: int = 50
) -> list[User]:
    users = await session.scalars(
        select(User).order_by(User.created_at).offset(offset).limit(limit)
    )
    return list(users.all())


async def create_user_service(
    session: AsyncSession, user_data: UserCreate
) -> User:
    email = user_data.email.lower()

    duplicate_user = await session.scalar(
        select(User).where(
            (User.username == user_data.username) | (User.email == email)
        )
    )

    if duplicate_user:
        raise ValueError('Username or email already exists.')

    new_user = User(
        username=user_data.username,
        email=email,
        hashed_password=get_password_hash(user_data.password),
        role=user_data.role,
    )

    session.add(new_user)

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ValueError('Username or email already exists.') from None

    await session.refresh(new_user)
    return new_user


async def update_user_service(
    session: AsyncSession,
    user_id: UUID,
    user_data: UserUpdate | AdminUserUpdate,
) -> User | None:
    target_user = await session.get(User, user_id)
    if not target_user:
        return None

    updated_fields = user_data.model_dump(exclude_unset=True)

    if 'password' in updated_fields:
        updated_fields['hashed_password'] = get_password_hash(
            updated_fields.pop('password')
        )

    if 'email' in updated_fields:
        updated_fields['email'] = updated_fields['email'].lower().strip()

    conflicting_user = await session.scalar(
        select(User).where(
            (User.id
            != user_id)
            & or_(
                User.username == updated_fields.get('username'),
                User.email == updated_fields.get('email'),
            ),
        )
    )
    if conflicting_user:
        raise ValueError('Username or email already exists.')

    is_losing_admin_access = (
        target_user.role == UserRole.ADMIN
        and target_user.is_active
        and (
            updated_fields.get('role', UserRole.ADMIN) != UserRole.ADMIN
            or updated_fields.get('is_active', True) is False
        )
    )
    if is_losing_admin_access:
        active_admins_count = await session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == UserRole.ADMIN, User.is_active.is_(True))
        )
        if active_admins_count <= 1:
            raise ValueError('Cannot remove the last active admin.')

    for field, value in updated_fields.items():
        setattr(target_user, field, value)

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ValueError('Username or email already exists.') from None

    await session.refresh(target_user)
    return target_user
