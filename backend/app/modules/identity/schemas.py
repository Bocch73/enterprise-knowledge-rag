"""Validated public schemas for registration, authentication, and users."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.modules.identity.models import User


class UserRegister(BaseModel):
    """Information required to create a local user account."""

    email: EmailStr
    display_name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("display_name")
    @classmethod
    def clean_display_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("display name must contain at least two visible characters")
        return cleaned


class UserResponse(BaseModel):
    """Safe user data; password hashes are deliberately absent."""

    id: UUID
    email: str
    display_name: str
    is_active: bool
    roles: list[str]
    created_at: datetime

    @classmethod
    def from_model(cls, user: User) -> "UserResponse":
        return cls(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            is_active=user.is_active,
            roles=sorted(role.code for role in user.roles),
            created_at=user.created_at,
        )


class TokenResponse(BaseModel):
    """OAuth-compatible bearer access token response."""

    access_token: str
    token_type: str = "bearer"  # noqa: S105 - protocol token type, not a credential
    expires_in: int
