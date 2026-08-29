"""FastAPI authentication dependencies."""

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.db.session import get_db_session
from app.modules.identity.models import User
from app.modules.identity.security import decode_access_token
from app.modules.identity.service import get_user_by_id

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]


async def get_current_user(
    request: Request,
    session: SessionDependency,
    token: Annotated[str, Depends(oauth2_scheme)],
) -> User:
    """Resolve and re-check the database user for every authenticated request."""
    settings: Settings = request.app.state.settings
    user_id = decode_access_token(token, settings)
    user = await get_user_by_id(session, user_id)
    if user is None or not user.is_active:
        raise AppError(
            code="authentication_required",
            message="Authentication is required",
            status_code=401,
        )
    request.state.actor_user_id = user.id
    return user


CurrentUserDependency = Annotated[User, Depends(get_current_user)]


async def get_current_admin(user: CurrentUserDependency) -> User:
    """Require the global administrator role for operational data."""
    if not user.has_role("admin"):
        raise AppError(
            code="permission_denied",
            message="Administrator role is required",
            status_code=403,
        )
    return user


AdminUserDependency = Annotated[User, Depends(get_current_admin)]
