# Worker

Celery process. It runs the only background task in the system, `ingest_document`. The API enqueues that name after a new upload. The steps, the retries, and the reason the API does not import this package are in the root README section [How Celery runs the ingest task](../README.md#how-celery-runs-the-ingest-task).

## What this process is

`celery_app.py` builds a Celery app named `aurelia` with `REDIS_URL` as the broker and imports `tasks.py`. That file registers `ingest_document`. Compose starts it as:

```bash
celery -A worker.celery_app:celery worker --loglevel=INFO
```

Locally, from the repo root, with the shared virtual environment:

```bash
PYTHONPATH=backend backend/.venv/bin/celery -A worker.celery_app:celery worker --loglevel=info
```

The API never imports `worker`. It sends the task by name through its own Celery client. Both sides must use the same `REDIS_URL`. This process also needs the same `DATABASE_URL`, `DATA_DIR`, and embedding settings as the API, because it reads the uploaded file and writes the chunks. In Compose the file volume is `aurelia_uploads` at `/app/data`.

`celery_app.py` puts `backend/` on `sys.path` before importing `app`. Ruff ignores E402 in that file on purpose.

## One message, one job

The message body is the job id. `ingest_document` attaches the trace headers that came with the message, then calls `app.ingest.pipeline.run_ingest`.

| Job status | Who sets it | What it means |
| --- | --- | --- |
| `pending` | API, when the row is created | The message may still be waiting in Redis. |
| `processing` | `run_ingest`, after it claims the row | Extract, chunk, and embed are in progress. |
| `completed` | `run_ingest`, after the chunks are stored | A later delivery of the same id returns without embedding again. |
| `failed` | `run_ingest` for a permanent error, or this task after retries | `failure_reason` is the text the library shows. |

A permanent error, such as a PDF with no text layer, is stored and the task returns. Celery then drops the message. A transient error, such as the embedder being unreachable, raises `TransientIngestError`. `max_retries=2` allows two more runs. The delay is `2 ** attempt` seconds and never more than 60. The attempt that still fails calls `mark_job_failed` and returns, so the message is not redelivered forever.

`task_acks_late` keeps the Redis message until the task function returns. A worker that dies mid-embed leaves the message for another delivery. Replacing that document's chunks makes the repeat safe. `worker_prefetch_multiplier=1` means a process reserves one message, not a batch.

On macOS the pool is `solo` so tracing starts in the same process as the task. Linux, including Compose, uses prefork. Each child runs `_init_worker` and configures its own traces there. The API lifespan does not run inside those children.

Chat on this process is used only when `PDF_READING_ORDER=llm`. The default `geometry` does not call a chat model. Embeddings still run, and in Compose they use the same LiteLLM settings as the API (`all-minilm` on host Ollama).

Tests do not start this process. `CELERY_TASK_ALWAYS_EAGER=true` makes the API call `run_ingest` itself.
