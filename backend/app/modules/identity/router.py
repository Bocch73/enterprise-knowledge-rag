"""Registration, login, and current-user HTTP endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.config import Settings
from app.modules.identity.dependencies import CurrentUserDependency, SessionDependency
from app.modules.identity.schemas import TokenResponse, UserRegister, UserResponse
from app.modules.identity.security import create_access_token
from app.modules.identity.service import authenticate_user, register_user

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: Request,
    registration: UserRegister,
    session: SessionDependency,
) -> UserResponse:
    user = await register_user(session, registration)
    request.state.actor_user_id = user.id
    request.state.audit_resource_id = user.id
    return UserResponse.from_model(user)


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    session: SessionDependency,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> TokenResponse:
    settings: Settings = request.app.state.settings
    user = await authenticate_user(session, form.username, form.password)
    request.state.actor_user_id = user.id
    request.state.audit_resource_id = user.id
    token = create_access_token(user.id, settings)
    return TokenResponse(
        access_token=token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=UserResponse)
async def current_user(user: CurrentUserDependency) -> UserResponse:
    return UserResponse.from_model(user)
