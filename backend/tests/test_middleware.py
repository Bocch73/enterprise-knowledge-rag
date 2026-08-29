"""Request identifier and security header tests."""

from uuid import UUID

from fastapi.testclient import TestClient


def test_request_id_is_generated_when_missing(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")

    generated_request_id = response.headers["X-Request-ID"]
    assert str(UUID(generated_request_id)) == generated_request_id


def test_safe_client_request_id_is_preserved(client: TestClient) -> None:
    response = client.get(
        "/api/v1/health/live",
        headers={"X-Request-ID": "frontend.request-123"},
    )

    assert response.headers["X-Request-ID"] == "frontend.request-123"


def test_unsafe_client_request_id_is_replaced(client: TestClient) -> None:
    response = client.get(
        "/api/v1/health/live",
        headers={"X-Request-ID": "contains spaces"},
    )

    assert response.headers["X-Request-ID"] != "contains spaces"
    UUID(response.headers["X-Request-ID"])


def test_baseline_security_headers_are_added(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"
    assert (
        response.headers["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'none'"
    )
