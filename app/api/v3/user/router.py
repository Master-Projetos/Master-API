from http import HTTPStatus
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.core.security import CurrentAdmin, CurrentUser, SessionDep
from app.api.v3.user.schemas import (
    AdminUserUpdate,
    UserCreate,
    UserPublic,
    UserUpdate,
)
from app.modules.user.services import (
    create_user_service,
    get_users_service,
    update_user_service,
)

router = APIRouter(prefix='/users', tags=['users'])


@router.post('', response_model=UserPublic, status_code=HTTPStatus.CREATED)
async def create_user(
    user_data: UserCreate, session: SessionDep, admin: CurrentAdmin
):
    try:
        return await create_user_service(session, user_data)
    except ValueError as error:
        raise HTTPException(status_code=HTTPStatus.CONFLICT, detail=str(error))


@router.get('', response_model=list[UserPublic])
async def list_users(
    session: SessionDep, admin: CurrentAdmin, offset: int = 0, limit: int = 100
):

    return await get_users_service(session, offset, limit)


@router.get('/me', response_model=UserPublic)
async def read_me(current_user: CurrentUser):
    return current_user


@router.patch('/me', response_model=UserPublic)
async def update_me(
    user_data: UserUpdate, session: SessionDep, current_user: CurrentUser
):
    try:
        return await update_user_service(session, current_user.id, user_data)
    except ValueError as error:
        raise HTTPException(status_code=HTTPStatus.CONFLICT, detail=str(error))


@router.patch('/{user_id}', response_model=UserPublic)
async def update_user(
    user_id: UUID,
    user_data: AdminUserUpdate,
    session: SessionDep,
    admin: CurrentAdmin,
):
    try:
        updated_user = await update_user_service(session, user_id, user_data)
    except ValueError as error:
        raise HTTPException(status_code=HTTPStatus.CONFLICT, detail=str(error))

    if not updated_user:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='User not found'
        )
    return updated_user
