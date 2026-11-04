"""Shared fixtures. Integration tests require PostgreSQL with pgvector."""

import os
from collections import abc

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry import trace
from sqlalchemy import create_engine, text

from app.core.config import Settings, get_settings
from app.core.telemetry import reset_telemetry
from app.db.session import reset_engine
from app.main import create_app


def _database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://aurelia:aurelia@localhost:5432/aurelia",
    )


@pytest.fixture(scope="session")
def database_url() -> str:
    url = _database_url()
    try:
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        engine.dispose()
    except Exception as exc:
        if os.environ.get("CI"):
            pytest.fail(f"PostgreSQL is required in CI: {exc}")
        pytest.skip(f"PostgreSQL with pgvector is not reachable: {exc}")
    return url


@pytest.fixture()
def settings(database_url: str, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    reset_engine()
    reset_telemetry()
    return Settings(
        database_url=database_url,
        celery_task_always_eager=True,
        seed_corpus=False,
        auth_required=False,
        llm_provider="fake",
        embedding_provider="fake",
        llm_retry_backoff_seconds=0,
        llm_max_attempts=3,
        langfuse_public_key=None,
        langfuse_secret_key=None,
        pdf_reading_order="geometry",
    )


@pytest.fixture()
def migrated(settings: Settings) -> Settings:
    get_settings.cache_clear()
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    engine = create_engine(settings.database_url)
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE chunks, jobs, documents CASCADE"))
    engine.dispose()
    reset_engine()
    return settings


@pytest.fixture()
def spans() -> abc.Iterator[InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    yield exporter
    exporter.clear()


@pytest.fixture()
def client(migrated: Settings, spans: InMemorySpanExporter) -> abc.Iterator[TestClient]:
    del spans
    application = create_app(migrated)
    with TestClient(application) as test_client:
        yield test_client
