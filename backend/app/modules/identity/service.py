"""Identity use cases independent of HTTP routing."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppError
from app.modules.identity.models import Role, User
from app.modules.identity.schemas import UserRegister
from app.modules.identity.security import (
    consume_dummy_password_check,
    hash_password,
    verify_password,
)


def normalize_email(email: str) -> str:
    """Use one stable representation before comparisons and storage."""
    return email.strip().lower()


async def get_user_by_id(session: AsyncSession, user_id: UUID) -> User | None:
    result = await session.execute(
        select(User).options(selectinload(User.roles)).where(User.id == user_id)
    )
    return result.scalar_one_or_none()


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    normalized_email = normalize_email(email)
    result = await session.execute(
        select(User).options(selectinload(User.roles)).where(User.email == normalized_email)
    )
    return result.scalar_one_or_none()


async def register_user(session: AsyncSession, registration: UserRegister) -> User:
    """Create a member account and translate uniqueness conflicts safely."""
    member_role = await session.scalar(select(Role).where(Role.code == "member"))
    if member_role is None:
        raise RuntimeError("required member role is missing; apply database migrations")

    user = User(
        email=normalize_email(str(registration.email)),
        display_name=registration.display_name,
        password_hash=hash_password(registration.password),
        roles=[member_role],
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exception:
        await session.rollback()
        raise AppError(
            code="email_already_registered",
            message="An account with this email already exists",
            status_code=409,
        ) from exception

    persisted_user = await get_user_by_id(session, user.id)
    if persisted_user is None:
        raise RuntimeError("newly registered user could not be reloaded")
    return persisted_user


async def authenticate_user(session: AsyncSession, email: str, password: str) -> User:
    """Verify credentials without revealing whether an email exists."""
    user = await get_user_by_email(session, email)
    if user is None:
        consume_dummy_password_check(password)
    if user is None or not verify_password(password, user.password_hash) or not user.is_active:
        raise AppError(
            code="invalid_credentials",
            message="Email or password is incorrect",
            status_code=401,
        )

    user.last_login_at = datetime.now(UTC)
    await session.commit()
    return user


async def list_users(session: AsyncSession) -> list[User]:
    """Return users in deterministic order for administrator workflows."""
    result = await session.execute(
        select(User).options(selectinload(User.roles)).order_by(User.created_at, User.id)
    )
    return list(result.scalars().unique())
