"""Shared fixtures backed by the isolated rag1_test PostgreSQL database."""

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text

from alembic import command
from app.core.config import Settings
from app.db.session import Database
from app.main import create_app

BACKEND_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def test_database_url() -> str:
    local_settings = Settings()  # type: ignore[call-arg]
    database_url = local_settings.test_database_url
    if database_url is None or not database_url.rsplit("/", maxsplit=1)[-1].endswith("_test"):
        raise RuntimeError("tests refuse to run unless RAG_TEST_DATABASE_URL ends with _test")
    return database_url


@pytest.fixture(scope="session", autouse=True)
def migrate_test_database(test_database_url: str) -> None:
    """Bring the disposable test database to the latest migration revision."""
    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))
    alembic_config.set_main_option("sqlalchemy.url", test_database_url)
    command.upgrade(alembic_config, "head")


@pytest.fixture
def settings(test_database_url: str, tmp_path: Path) -> Settings:
    """Return isolated settings that never enable development debug behavior."""
    return Settings(
        environment="test",
        debug=False,
        log_level="CRITICAL",
        database_url=test_database_url,
        test_database_url=test_database_url,
        jwt_secret_key=SecretStr("test-only-secret-key-with-more-than-32-characters"),
        object_storage_path=tmp_path / "objects",
    )


@pytest.fixture(autouse=True)
def clean_test_data(settings: Settings) -> None:
    """Delete business rows before every test while preserving seeded roles."""

    async def clean() -> None:
        database = Database(settings)
        try:
            async with database.engine.begin() as connection:
                await connection.execute(text("TRUNCATE TABLE users RESTART IDENTITY CASCADE"))
        finally:
            await database.dispose()

    asyncio.run(clean())


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    """Create a fresh application for every test."""
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """Call the ASGI application without opening a network port."""
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
