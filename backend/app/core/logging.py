"""Structured logs that carry the trace and the job id."""

from __future__ import annotations

import logging
from contextvars import ContextVar

from opentelemetry import trace

job_id_var: ContextVar[str] = ContextVar("job_id", default="")


class _ContextFilter(logging.Filter):
    """Attach the current trace id and ingest job id to each log record."""
    def filter(self, record: logging.LogRecord) -> bool:
        """Copy context vars onto the record. Logging always keeps the record."""
        span = trace.get_current_span()
        context = span.get_span_context()
        if context.is_valid:
            record.trace_id = format(context.trace_id, "032x")
            record.span_id = format(context.span_id, "016x")
        else:
            record.trace_id = "-"
            record.span_id = "-"
        record.job_id = job_id_var.get() or "-"
        return True


def configure_logging(level: str) -> None:
    """Install a single structured format for the process."""
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s trace=%(trace_id)s span=%(span_id)s "
            "job=%(job_id)s %(message)s"
        )
    )
    handler.addFilter(_ContextFilter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
