"""Registration, password, bearer token, and authorization integration tests."""

import asyncio
from typing import cast

from fastapi.testclient import TestClient

from app.cli.create_admin import create_or_promote_admin
from app.core.config import Settings
from app.db.session import Database
from app.modules.identity.service import get_user_by_email


def register_user(
    client: TestClient,
    *,
    email: str = "learner@example.com",
    display_name: str = "RAG Learner",
    password: str = "CorrectHorseBattery1!",
) -> dict[str, object]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "display_name": display_name, "password": password},
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, object], response.json())


def login_user(
    client: TestClient,
    *,
    email: str = "learner@example.com",
    password: str = "CorrectHorseBattery1!",
) -> str:
    response = client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 1800
    return str(body["access_token"])


def authorization_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_register_login_and_read_current_user(client: TestClient) -> None:
    registered = register_user(client, email="Learner@Example.COM")

    assert registered["email"] == "learner@example.com"
    assert registered["roles"] == ["member"]
    assert "password" not in registered
    assert "password_hash" not in registered

    token = login_user(client)
    response = client.get("/api/v1/auth/me", headers=authorization_header(token))

    assert response.status_code == 200
    assert response.json()["id"] == registered["id"]


def test_duplicate_email_is_case_insensitive(client: TestClient) -> None:
    register_user(client, email="duplicate@example.com")

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "DUPLICATE@example.com",
            "display_name": "Second Account",
            "password": "AnotherStrongPassword2!",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_already_registered"


def test_password_policy_rejects_short_password(client: TestClient) -> None:
    rejected_password = "dont-leak-7"
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "short@example.com",
            "display_name": "Short Pass",
            "password": rejected_password,
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_error"
    assert rejected_password not in response.text


def test_wrong_and_unknown_credentials_share_public_error(client: TestClient) -> None:
    register_user(client)

    wrong = client.post(
        "/api/v1/auth/login",
        data={"username": "learner@example.com", "password": "WrongPassword123!"},
    )
    unknown = client.post(
        "/api/v1/auth/login",
        data={"username": "missing@example.com", "password": "WrongPassword123!"},
    )

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["code"] == unknown.json()["error"]["code"]
    assert wrong.headers["WWW-Authenticate"] == "Bearer"


def test_tampered_token_is_rejected(client: TestClient) -> None:
    register_user(client)
    token = login_user(client)
    tampered_token = f"{token[:-1]}{'a' if token[-1] != 'a' else 'b'}"

    response = client.get(
        "/api/v1/auth/me",
        headers=authorization_header(tampered_token),
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_access_token"
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_member_cannot_use_global_admin_endpoint(client: TestClient) -> None:
    register_user(client)
    token = login_user(client)

    response = client.get("/api/v1/admin/users", headers=authorization_header(token))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


def test_administrator_can_list_users(client: TestClient, settings: Settings) -> None:
    asyncio.run(
        create_or_promote_admin(
            "admin@example.com",
            "Local Admin",
            "CorrectHorseBattery1!",
            settings,
        )
    )
    # The bootstrap operation is intentionally idempotent.
    asyncio.run(
        create_or_promote_admin(
            "admin@example.com",
            "Local Admin",
            "CorrectHorseBattery1!",
            settings,
        )
    )
    token = login_user(client, email="admin@example.com")

    response = client.get("/api/v1/admin/users", headers=authorization_header(token))

    assert response.status_code == 200
    assert response.json()[0]["roles"] == ["admin", "member"]


def test_deactivated_user_cannot_reuse_existing_token(
    client: TestClient,
    settings: Settings,
) -> None:
    register_user(client)
    token = login_user(client)

    async def deactivate() -> None:
        database = Database(settings)
        try:
            async with database.session_factory() as session:
                user = await get_user_by_email(session, "learner@example.com")
                assert user is not None
                user.is_active = False
                await session.commit()
        finally:
            await database.dispose()

    asyncio.run(deactivate())
    response = client.get("/api/v1/auth/me", headers=authorization_header(token))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"
