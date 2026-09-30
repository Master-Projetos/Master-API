from http import HTTPStatus
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response

from app.api.v3.api_keys.schemas import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyPublic,
)
from app.core.security import CurrentAdmin, CurrentUser, SessionDep
from app.modules.api_key.services import (
    create_api_key_service,
    list_api_keys_service,
    revoke_api_key_service,
)

# JWT only (CurrentUser/CurrentAdmin): an API key can never manage keys
router = APIRouter(prefix='/api-keys', tags=['api-keys'])


@router.post('', response_model=ApiKeyCreated, status_code=HTTPStatus.CREATED)
async def create_api_key(
    key_data: ApiKeyCreate,
    response: Response,
    session: SessionDep,
    current_user: CurrentUser,
):
    try:
        api_key, raw_key = await create_api_key_service(
            session,
            current_user.id,
            key_data.name,
            key_data.scopes,
            key_data.expires_in_days,
        )
    except ValueError as error:
        raise HTTPException(status_code=HTTPStatus.CONFLICT, detail=str(error))

    # The plain key must not be cached by proxies or browsers
    response.headers['Cache-Control'] = 'no-store'

    return ApiKeyCreated(
        **ApiKeyPublic.model_validate(api_key).model_dump(), key=raw_key
    )


@router.get('', response_model=list[ApiKeyPublic])
async def list_my_api_keys(session: SessionDep, current_user: CurrentUser):
    return await list_api_keys_service(session, current_user.id)


@router.delete('/{key_id}', status_code=HTTPStatus.NO_CONTENT)
async def revoke_my_api_key(
    key_id: UUID, session: SessionDep, current_user: CurrentUser
):
    # 404 (not 403) for other users' keys, so ids can't be probed
    if not await revoke_api_key_service(session, key_id, current_user.id):
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='API key not found'
        )


@router.get('/admin', response_model=list[ApiKeyPublic])
async def list_all_api_keys(
    session: SessionDep, admin: CurrentAdmin, user_id: UUID | None = None
):
    return await list_api_keys_service(session, user_id)


@router.delete('/admin/{key_id}', status_code=HTTPStatus.NO_CONTENT)
async def revoke_any_api_key(
    key_id: UUID, session: SessionDep, admin: CurrentAdmin
):
    if not await revoke_api_key_service(session, key_id, owner_id=None):
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='API key not found'
        )
