"""Public error contract tests."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import AppError


def test_not_found_uses_common_error_shape(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist", headers={"X-Request-ID": "not-found-1"})

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "http_404",
            "message": "Not Found",
            "request_id": "not-found-1",
            "details": None,
        }
    }


def test_validation_error_does_not_echo_input(app: FastAPI, client: TestClient) -> None:
    @app.get("/_test/validated")
    async def validated_endpoint(limit: int) -> dict[str, int]:
        return {"limit": limit}

    response = client.get("/_test/validated?limit=secret-value")

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "request_validation_error"
    assert body["error"]["details"][0]["location"] == ["query", "limit"]
    assert "secret-value" not in response.text


def test_known_application_error_is_translated(app: FastAPI, client: TestClient) -> None:
    @app.get("/_test/conflict")
    async def conflict_endpoint() -> None:
        raise AppError(
            code="duplicate_resource", message="Resource already exists", status_code=409
        )

    response = client.get("/_test/conflict", headers={"X-Request-ID": "conflict-1"})

    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "duplicate_resource",
        "message": "Resource already exists",
        "request_id": "conflict-1",
        "details": None,
    }


def test_unexpected_error_is_hidden(app: FastAPI, client: TestClient) -> None:
    @app.get("/_test/explode")
    async def explode_endpoint() -> None:
        raise RuntimeError("database-password-should-not-leak")

    response = client.get("/_test/explode", headers={"X-Request-ID": "explode-1"})

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_server_error",
            "message": "Unexpected server error",
            "request_id": "explode-1",
            "details": None,
        }
    }
    assert "database-password-should-not-leak" not in response.text
