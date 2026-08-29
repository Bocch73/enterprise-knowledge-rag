"""Global administrator endpoints."""

from fastapi import APIRouter

from app.modules.identity.dependencies import AdminUserDependency, SessionDependency
from app.modules.identity.schemas import UserResponse
from app.modules.identity.service import list_users

router = APIRouter()


@router.get("/users", response_model=list[UserResponse])
async def users(
    _admin: AdminUserDependency,
    session: SessionDependency,
) -> list[UserResponse]:
    return [UserResponse.from_model(user) for user in await list_users(session)]
