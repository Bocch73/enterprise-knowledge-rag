"""Focused password and signed-token security tests."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.core.errors import AppError
from app.modules.identity.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_is_stored_as_argon2_hash() -> None:
    password = "CorrectHorseBattery1!"
    password_hash = hash_password(password)

    assert password_hash != password
    assert password_hash.startswith("$argon2id$")
    assert verify_password(password, password_hash) is True
    assert verify_password("WrongPassword123!", password_hash) is False


def test_expired_access_token_is_rejected(settings: Settings) -> None:
    issued_long_ago = datetime.now(UTC) - timedelta(hours=2)
    token = create_access_token(uuid4(), settings, now=issued_long_ago)

    with pytest.raises(AppError, match="invalid or expired"):
        decode_access_token(token, settings)
