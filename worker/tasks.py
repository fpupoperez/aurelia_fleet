"""Ingest task. Retries transient failures and records a final failed state."""

from celery.utils.log import get_task_logger
from opentelemetry import context as otel_context
from opentelemetry.propagate import extract

from app.domain.errors import TransientIngestError
from app.ingest.pipeline import mark_job_failed, run_ingest
from worker.celery_app import celery

logger = get_task_logger(__name__)


@celery.task(bind=True, name="ingest_document", max_retries=2)
def ingest_document(self, job_id: str) -> None:
    """Process one upload. Redelivery of a completed job is a no-op."""
    headers = getattr(self.request, "headers", None) or {}
    token = otel_context.attach(extract(headers))
    try:
        run_ingest(job_id)
    except TransientIngestError as exc:
        if self.request.retries >= self.max_retries:
            mark_job_failed(job_id, exc.message)
            logger.error("Ingest retries exhausted for %s", job_id)
            return
        raise self.retry(exc=exc, countdown=min(60, 2**self.request.retries)) from exc
    finally:
        otel_context.detach(token)
