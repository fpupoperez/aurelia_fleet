"""OpenTelemetry setup. Langfuse receives spans when its keys are set."""

from __future__ import annotations

import base64
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from urllib.parse import quote

from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.core.config import Settings

logger = logging.getLogger(__name__)

_configured = False

_retrieval_latency = None
_llm_latency = None
_llm_tokens = None
_ingest_chunks = None
_jobs = None
_mcp_calls = None


def reset_telemetry() -> None:
    """Allow tests to configure tracing again."""
    global _configured
    _configured = False


def configure_telemetry(settings: Settings, service_name: str) -> None:
    """Export traces to Langfuse when keys are present. Otherwise leave tracing alone."""
    global _configured, _retrieval_latency, _llm_latency, _llm_tokens, _ingest_chunks, _jobs, _mcp_calls
    if _configured:
        return
    _configured = True
    resource = Resource.create({"service.name": service_name})
    if settings.langfuse_public_key and settings.langfuse_secret_key:
        token = base64.b64encode(
            f"{settings.langfuse_public_key}:{settings.langfuse_secret_key}".encode()
        ).decode()
        host = settings.langfuse_host.rstrip("/")
        endpoint = f"{host}/api/public/otel/v1/traces"
        headers = {"Authorization": f"Basic {token}"}
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            provider = TracerProvider(resource=resource)
            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, headers=headers)))
            trace.set_tracer_provider(provider)
        except Exception:
            logger.warning("Langfuse trace export is not active", exc_info=True)
        _configure_metrics(settings, resource, token, host)
    else:
        metrics.set_meter_provider(MeterProvider(resource=resource))
    meter = metrics.get_meter("aurelia")
    _retrieval_latency = meter.create_histogram("aurelia.retrieval.latency", unit="ms")
    _llm_latency = meter.create_histogram("aurelia.llm.latency", unit="ms")
    _llm_tokens = meter.create_counter("aurelia.llm.tokens")
    _ingest_chunks = meter.create_counter("aurelia.ingest.chunks")
    _jobs = meter.create_counter("aurelia.jobs")
    _mcp_calls = meter.create_counter("aurelia.mcp.calls")


def _configure_metrics(settings: Settings, resource: Resource, token: str, host: str) -> None:
    """Register counters and histograms for ingest, search, and chat."""
    try:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

        exporter = OTLPMetricExporter(
            endpoint=f"{host}/api/public/otel/v1/metrics",
            headers={"Authorization": f"Basic {token}"},
        )
        reader = PeriodicExportingMetricReader(exporter, export_interval_millis=60000)
        metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))
    except Exception:
        logger.warning("Langfuse metric export is not active", exc_info=True)
        metrics.set_meter_provider(MeterProvider(resource=resource))


def tracer() -> trace.Tracer:
    """The process tracer. Spans are no-ops until configure_telemetry has run."""
    return trace.get_tracer("aurelia")


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[trace.Span]:
    """Start a span and set only attributes that have a value."""
    with tracer().start_as_current_span(name) as current:
        for key, value in attributes.items():
            if value is not None:
                current.set_attribute(key, value)
        yield current


def record_retrieval(duration_ms: float, *, abstained: bool) -> None:
    """Count a search and how long it took, including abstentions."""
    if _retrieval_latency is not None:
        _retrieval_latency.record(duration_ms, {"abstained": str(abstained).lower()})


def record_llm(duration_ms: float, *, input_tokens: int, output_tokens: int, model: str) -> None:
    """Count a chat call, its latency, and its token totals."""
    if _llm_latency is not None:
        _llm_latency.record(duration_ms, {"model": model})
    if _llm_tokens is not None:
        _llm_tokens.add(input_tokens, {"direction": "input", "model": model})
        _llm_tokens.add(output_tokens, {"direction": "output", "model": model})


def record_chunks(count: int) -> None:
    """Count chunks written by ingest."""
    if _ingest_chunks is not None:
        _ingest_chunks.add(count)


def record_job(status: str) -> None:
    """Count a job reaching completed or failed."""
    if _jobs is not None:
        _jobs.add(1, {"status": status})


def record_mcp(operation_id: str, *, success: bool, duration_ms: float) -> None:
    """Count one MCP tool call and whether the API envelope said success."""
    if _mcp_calls is not None:
        _mcp_calls.add(1, {"operation_id": operation_id, "success": str(success).lower()})


def langfuse_auth_header(settings: Settings) -> str | None:
    """Basic auth for the browser trace proxy. None when Langfuse keys are unset."""
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return None
    token = base64.b64encode(
        f"{settings.langfuse_public_key}:{settings.langfuse_secret_key}".encode()
    ).decode()
    return f"Basic {token}"


def otel_header_value(settings: Settings) -> str | None:
    """Header string for OTEL_EXPORTER_OTLP_HEADERS, kept for tests and operators."""
    header = langfuse_auth_header(settings)
    if header is None:
        return None
    return f"Authorization={quote(header, safe='')}"
