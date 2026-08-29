"""Liveness, readiness, and OpenAPI tests."""

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_liveness_reports_process_identity(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "Enterprise Knowledge RAG",
        "version": "0.1.0",
        "environment": "test",
    }


def test_readiness_reports_application_check(client: TestClient) -> None:
    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"application": "up", "database": "up"},
    }


def test_readiness_returns_503_when_dependency_fails(app: FastAPI, client: TestClient) -> None:
    async def failing_database_check() -> None:
        raise RuntimeError("database is unavailable")

    app.state.readiness_checks = {"database": failing_database_check}

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"database": "down"},
    }


def test_openapi_contains_health_endpoints(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/health/live" in paths
    assert "/api/v1/health/ready" in paths
    assert "/api/v1/auth/register" in paths
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/knowledge-bases" in paths
