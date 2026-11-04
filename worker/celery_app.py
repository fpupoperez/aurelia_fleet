"""Celery application. The API enqueues by task name and does not import this module."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_BACKEND = _ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from celery import Celery
from celery.signals import worker_process_init

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.telemetry import configure_telemetry

settings = get_settings()
configure_logging(settings.log_level)

celery = Celery("aurelia", broker=settings.redis_url, include=["worker.tasks"])
celery.conf.task_acks_late = True
celery.conf.worker_prefetch_multiplier = 1
celery.conf.broker_connection_retry_on_startup = True
if sys.platform == "darwin":
    # Celery's prefork pool uses spawn on macOS, and the fast task tracer
    # then runs before worker-local state exists. Solo is one process and
    # still runs the same task. Linux Compose keeps the prefork default.
    celery.conf.worker_pool = "solo"


@worker_process_init.connect
def _init_worker(**_kwargs: object) -> None:
    """Configure logging and traces inside each Celery child, which does not run the API lifespan."""
    configure_telemetry(get_settings(), "aurelia-worker")
    try:
        from opentelemetry.instrumentation.celery import CeleryInstrumentor

        CeleryInstrumentor().instrument()
    except Exception:
        pass
