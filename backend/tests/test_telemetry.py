"""Langfuse export stays off when no keys are configured."""

import os

from app.core.config import Settings
from app.core.telemetry import configure_telemetry, reset_telemetry


def test_no_exporter_without_langfuse_keys(monkeypatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    reset_telemetry()
    configure_telemetry(Settings(langfuse_public_key=None, langfuse_secret_key=None), "test")
    assert "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT" not in os.environ
