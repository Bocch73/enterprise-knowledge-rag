"""Password hashing and signed access token primitives."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash

from app.core.config import Settings
from app.core.errors import AppError

password_hasher = PasswordHash.recommended()
_DUMMY_PASSWORD_HASH = password_hasher.hash("dummy-password-never-accepted")


def hash_password(password: str) -> str:
    """Transform a plaintext password into a non-reversible Argon2 hash."""
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Compare a candidate password with a stored hash."""
    return password_hasher.verify(password, password_hash)


def consume_dummy_password_check(password: str) -> None:
    """Reduce user-enumeration timing differences for unknown accounts."""
    password_hasher.verify(password, _DUMMY_PASSWORD_HASH)


def create_access_token(
    user_id: UUID,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> str:
    """Create a signed, short-lived token that identifies one user."""
    issued_at = now or datetime.now(UTC)
    expires_at = issued_at + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": issued_at,
        "exp": expires_at,
        "jti": str(uuid4()),
    }
    return jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str, settings: Settings) -> UUID:
    """Validate token signature, intended use, issuer, audience, and expiry."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["sub", "type", "iss", "aud", "iat", "exp", "jti"]},
        )
        if payload["type"] != "access":
            raise InvalidTokenError("unexpected token type")
        return UUID(str(payload["sub"]))
    except (InvalidTokenError, TypeError, ValueError) as exception:
        raise AppError(
            code="invalid_access_token",
            message="Access token is invalid or expired",
            status_code=401,
        ) from exception
