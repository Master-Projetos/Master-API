from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm

from app.core.security import (
    SessionDep,
    authenticate_user_service,
    create_access_token,
)

router = APIRouter(prefix='/auth', tags=['auth'])


@router.post('/token')
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: SessionDep,
):
    user = await authenticate_user_service(
        session, email=form_data.username, password=form_data.password
    )

    if not user:
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED,
            detail='Incorrect email or password',
            headers={'WWW-Authenticate': 'Bearer'},
        )

    access_token = create_access_token(user.id)

    return {'access_token': access_token, 'token_type': 'bearer'}
