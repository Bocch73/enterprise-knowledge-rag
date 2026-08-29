"""Static deployment contracts that do not require Docker on the developer machine."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def read_project_file(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_continuous_integration_uses_isolated_real_dependencies() -> None:
    workflow = read_project_file(".github/workflows/quality-gates.yml")

    assert "pgvector/pgvector:0.8.6-pg17-bookworm" in workflow
    assert "POSTGRES_DB: rag1_test" in workflow
    assert workflow.count("CREATE EXTENSION IF NOT EXISTS vector") == 2
    assert "generation-provider deterministic" in workflow
    assert "DEEPSEEK_API_KEY" not in workflow
    assert "pull_request_target" not in workflow
    assert "permissions:\n  contents: read" in workflow


def test_runtime_images_drop_root_and_ignore_local_secrets() -> None:
    backend_dockerfile = read_project_file("backend/Dockerfile")
    frontend_dockerfile = read_project_file("frontend/Dockerfile")
    backend_ignore = read_project_file("backend/.dockerignore")

    assert "ARG PYTHON_VERSION=3.11.16" in backend_dockerfile
    assert "FROM python:${PYTHON_VERSION}-slim-bookworm" in backend_dockerfile
    assert "USER 10001:10001" in backend_dockerfile
    assert "pip install --upgrade pip" not in backend_dockerfile
    assert "USER 101:101" in frontend_dockerfile
    assert "HEALTHCHECK" in backend_dockerfile
    assert ".env.*" in backend_ignore


def test_compose_keeps_data_services_internal_and_uses_secrets() -> None:
    compose = read_project_file("deploy/compose.production.yml")

    assert "POSTGRES_PASSWORD_FILE: /run/secrets/postgres_admin_password" in compose
    assert "database_password" in compose
    assert "POSTGRES_USER: postgres" in compose
    assert "POSTGRES_USER: rag_app" not in compose
    assert "init-app-role.sh" in compose
    assert "service_completed_successfully" in compose
    assert "internal: true" in compose
    assert "5432:5432" not in compose
    assert "read_only: true" in compose
    assert "no-new-privileges:true" in compose


def test_database_initialization_creates_a_limited_application_role() -> None:
    initialization = read_project_file("deploy/postgres/init-app-role.sh")

    assert "CREATE EXTENSION IF NOT EXISTS vector" in initialization
    assert "NOSUPERUSER" in initialization
    assert "NOCREATEDB" in initialization
    assert "NOCREATEROLE" in initialization
    assert "ALTER DATABASE" in initialization


def test_frontend_proxy_preserves_streaming_and_hides_metrics() -> None:
    nginx = read_project_file("frontend/nginx.conf")

    assert "location = /metrics" in nginx
    assert "return 404;" in nginx
    assert "proxy_buffering off;" in nginx
    assert "client_max_body_size 20m;" in nginx
