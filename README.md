# Aurelia Fleet manuals

Internal assistant for Aurelia Fleet Services. An administrator uploads a PDF, Markdown, or text manual. A worker extracts the text, chunks it, embeds it, and stores it in PostgreSQL with pgvector. A technician asks a question and gets an answer with citations, or an explicit refusal when the manuals do not support one.

Service details live next to the code: [backend/README.md](backend/README.md), [worker/README.md](worker/README.md), [frontend/README.md](frontend/README.md), [mcp/README.md](mcp/README.md), [infra/README.md](infra/README.md). Design notes that are easy to get wrong are in [DECISIONS.md](DECISIONS.md). The chunking and retrieval choices, and why they were made, are in [QUESTIONS.md](QUESTIONS.md).

## Architecture

```text
browser (5173)  -- /api -->  API (8000)  -- SQL -->  Postgres + pgvector (5432)
       |                         |                         ^
       | OTLP                    | Celery                  |
       +--> /api/v1/otel         v                         |
                         Redis (6379) --> worker ----------+
                         MCP (8001) ---- HTTP ----> API
                         API and worker --> Langfuse (3000) when keys are set
                         API chat/embeddings --> LiteLLM --> Ollama, vLLM, or a hosted model
```

| Piece | Role |
| --- | --- |
| API | Upload, list, download, ask, aliases, OpenAPI. Seeds `corpus/` when the tenant library is empty. |
| Worker | Celery task `ingest_document`. Extract, chunk, embed, store. |
| Frontend | Library, ask, aliases. Vite proxies `/api` to the API. |
| MCP | One tool per API `operationId`. It calls the HTTP API and does not open the database. |
| Postgres | Documents, jobs, chunks (`vector(384)`), alias groups. |
| Redis | Celery broker only. |
| Langfuse | Trace store. It is not the language model. |

Every JSON response uses `{session_auth, errors, success, data}`. `download_document` is the exception: the body is the file, streamed in 64 KB chunks. A missing document is still the JSON error envelope.

Rows are scoped by `tenant_id`. With `AUTH_REQUIRED=false` the tenant is `aurelia`. With `AUTH_REQUIRED=true` it comes from `session_auth.tenantId` in the bearer JWT. Another tenant's id is a 404.

## Ingest

1. The API checks type (PDF, Markdown, plain text) and the 15 MB limit, hashes the bytes, and stores `{data_dir}/uploads/{sha256}{suffix}`. The same hash for the same tenant returns the existing job and does not ingest again.
2. Maker, model, and title may be omitted. The API reads them from the file: the largest short heading on the first PDF page (split display letters such as `C` + `FA` + `Adapter` join into `CFA Adapter`), a Markdown heading, a product code such as `HX-200`, and a brand token such as Ruptela or Aurelia. A name the caller typed wins.
3. The worker extracts text. PDF columns are read top to bottom from positioned blocks. `PDF_READING_ORDER=llm` may reorder a multi-column page and is kept only when it does not add words. A page with no text layer fails the job. OCR is not implemented.
4. Pages are chunked, embedded, and written with the active `embedding_model`. A completed job is not embedded again. A retry replaces that document's chunks.

## How Celery runs the ingest task

Celery is the queue between the upload request and the slow work. Redis holds the message. Postgres holds the job status the library polls. There is one task, named `ingest_document`. It receives the job id and calls `run_ingest`.

The API does not import the worker. After it has stored the file and a job row with status `pending`, it opens its own Celery client on the same broker (`REDIS_URL`) and calls `send_task("ingest_document", args=[job_id])`. The HTTP response returns at that moment. A busy or down broker leaves the job `pending`. The UI polls `GET /jobs/{id}` until the status is `completed` or `failed`.

The worker process is a separate container, or this command from the repo root:

```bash
PYTHONPATH=backend backend/.venv/bin/celery -A worker.celery_app:celery worker --loglevel=info
```

`worker.celery_app` builds the Celery app named `aurelia`, points it at Redis, and imports `worker.tasks`, which registers `ingest_document`. The worker then waits on Redis. Each message is one job id.

What the worker does with that message:

1. It restores the upload's trace from the message headers, so the ingest spans continue the request that enqueued the job.
2. `run_ingest` loads the job. Status `completed` returns immediately, so a second delivery does not embed again.
3. It sets the job to `processing`, reads the file from the shared upload directory, chunks it, embeds it, and replaces that document's chunks.
4. It sets the job to `completed`.

Failures take two paths:

- A permanent failure, such as a PDF with no text layer, is written on the job as `failed` with the reason. The task returns normally, so Celery does not run it again.
- A transient failure, such as the embedding service being down, raises `TransientIngestError`. The task allows two retries (`max_retries=2`, three runs in total). The wait is `2 ** attempt` seconds, capped at 60. After the last retry the worker stores `failed` and returns, so Redis stops redelivering that message.

The worker acknowledges the Redis message only when the task function returns (`task_acks_late`). If the process dies in the middle, Redis delivers the same job id again. The completed-job check and the chunk replace make that delivery safe. Each process takes one message at a time (`worker_prefetch_multiplier=1`), so a long embed does not sit unread in a private buffer while another process is free.

On macOS the pool is `solo`, one process, because Celery's prefork pool breaks tracing there. The Linux image used by Compose keeps the prefork pool, several child processes. Each child configures its own traces when it starts. The API process never does that setup for them.

Tests set `CELERY_TASK_ALWAYS_EAGER=true`. The API then calls `run_ingest` in the request and does not talk to Redis. Asking a question never goes through Celery. Only ingest does. Chat on the worker runs only when `PDF_READING_ORDER=llm`. The default reading order does not call a model. The embedding call does.

## Chunks

Defaults: `CHUNK_SIZE=800`, `CHUNK_OVERLAP=120`. Both are character counts, not tokens. About 800 characters is a short quotable passage (roughly 120–200 tokens) rather than a whole datasheet page, so a citation stays on one fact and several passages still fit in a prompt.

Why these values:

- Structure comes first. A PDF chunk never crosses a printed page, so the stored page is the page a technician can open. A Markdown heading starts a new section, and that section index is stored as the page. Plain text is one page.
- The window breaks on a space in the second half of the slice, so it does not cut a word.
- Overlap is 120 characters, about 15 percent, and only inside that same page. The next window still contains the tail of the previous sentence when a torque or a voltage range sits on the boundary. Overlap does not leak text onto the next page. If overlap is greater than or equal to size, it is reduced to one fifth of the size.
- Empty text produces no chunk. A file with no extractable text fails the job.

`CHUNK_SIZE` must be at least 200. Changing it does not rewrite manuals already stored. Re-upload, or re-embed, to apply a new size.

## Ask path

1. Maker and model catalog questions are answered from document metadata. No chat call.
2. Supply voltage and operating-temperature comparisons are read from the printed ranges. "More than 12 V" uses the upper bound of a power-supply range. Storage and charging temperatures do not count. "What's the higher voltage" asks for the maximum of those upper bounds. The named maker, when the question includes one, limits the set.
3. Otherwise search is hybrid: pgvector cosine distance plus PostgreSQL full text (`simple`, so part numbers are not stemmed), fused with reciprocal rank (`RRF_K=60`). A passage that contains the question's content words is kept even when its distance is past the ceiling. Alias groups make two spellings one feature. A one-letter typo of a question word such as "supoorting" is folded back to "supporting" and is not required to appear on the page.
4. Tests and a process started with no provider variables use `LLM_PROVIDER=fake`. A word match returns the matching sentences directly, and a comparison returns the checked reading. The fake chat model only overlaps words. It does not reason. Embeddings are a hash into 384 dimensions.
5. The Docker stack uses `LLM_PROVIDER=litellm` and `EMBEDDING_PROVIDER=litellm`. Those readings are the evidence, and the chat model writes the sentences. It is told the checked reading and must not move a device onto a number its excerpt does not show. If the model is down or its JSON is unreadable, the direct reading is returned. A refusal because the manuals lack the fact is HTTP 200 with `answered: false`. A provider that is down is HTTP 503 and still returns the passages.

The fake embedder is a bag-of-words hash into 384 dimensions. Overlapping words usually land near cosine distance 0.55–0.63. The ceiling is `MAX_COSINE_DISTANCE=0.64`. Neighbors within `RETRIEVAL_NEIGHBOR_MARGIN=0.03` are kept. The fused-score floor is `MIN_FUSED_SCORE=0.01`. A question that names a library title or model does not use that ceiling. A passage that contains the question's content words is kept even when its distance is past that ceiling, so a real embedder does not have to match the hash calibration. Details and the calibration set are in [DECISIONS.md](DECISIONS.md). `make eval` runs that set with the fake embedder.

The column is `vector(384)`. Docker embeddings use Ollama `all-minilm`, which returns 384 values. `nomic-embed-text` emits 768 and is not used. The API refuses to start a provider whose dimension does not match the column. After changing the embedding model, re-embed stored chunks with `reindex_embeddings`. Search only reads rows whose `embedding_model` matches the active model.

## Environment

Compose reads `infra/.env`. A process started on the host reads a `.env` in the working directory. Names are the settings fields in uppercase. Copy from [.env.example](.env.example).

| Variable | Default | Purpose |
| --- | --- | --- |
| `LLM_PROVIDER` | `fake` in code and tests; `litellm` in Compose | `fake` or `litellm`. There is no third provider class. |
| `EMBEDDING_PROVIDER` | same split | Chat and embeddings are chosen separately. |
| `LLM_MODEL` | `gpt-4o-mini` in code; `openai/llama3.1:8b` in Compose | LiteLLM model id. |
| `LLM_API_BASE` | empty in code; host Ollama in Compose | OpenAI-compatible base URL. |
| `LLM_API_KEY` | empty | Any non-empty string for a local server that ignores the key. |
| `EMBEDDING_MODEL` | `text-embedding-3-small` in code; `openai/all-minilm` in Compose | Used when the embedding provider is `litellm`. |
| `EMBEDDING_DIMENSION` | `384` | Must match `vector(384)`. |
| `PDF_READING_ORDER` | `geometry` | `geometry` or `llm`. |
| `CHUNK_SIZE` | `800` | Characters. |
| `CHUNK_OVERLAP` | `120` | Characters, inside one page. |
| `DATABASE_URL` | local `aurelia` database | SQLAlchemy URL. |
| `REDIS_URL` | `redis://localhost:6379/0` | Celery broker. |
| `DATA_DIR` | repo `data/` | Upload bytes. In Compose this is the `aurelia_uploads` volume at `/app/data`. |
| `AUTH_REQUIRED` | `false` | |
| `LANGFUSE_PUBLIC_KEY` | empty outside Compose | Traces are exported only when both keys are set. |
| `LANGFUSE_SECRET_KEY` | empty outside Compose | |
| `LANGFUSE_HOST` | `http://localhost:3000` | Compose sets `http://langfuse-web:3000` for the API and worker. |

### Local Ollama

Ollama speaks the OpenAI API. Compose points LiteLLM at it for chat and for embeddings. `infra/.env` holds the same values, and they are the defaults in `docker-compose.yml` when a variable is unset:

```bash
LLM_PROVIDER=litellm
LLM_MODEL=openai/llama3.1:8b
LLM_API_BASE=http://host.docker.internal:11434/v1
LLM_API_KEY=ollama
EMBEDDING_PROVIDER=litellm
EMBEDDING_MODEL=openai/all-minilm
EMBEDDING_API_BASE=http://host.docker.internal:11434/v1
EMBEDDING_API_KEY=ollama
EMBEDDING_DIMENSION=384
```

```bash
ollama pull llama3.1:8b
ollama pull all-minilm
```

PDF text is still read from the page geometry. Set `PDF_READING_ORDER=llm` only when a multi-column page should be reordered by the same chat model. The result is kept only when it adds no words.

Pytest's `settings` fixture and CI set both providers to `fake`. A test does not call Ollama.

The API and worker containers map `host.docker.internal` to the host. Recreate both after changing the file, then re-embed chunks that were stored with another model:

```bash
docker compose -f infra/docker-compose.yml up -d --no-deps --build --force-recreate api worker
docker compose -f infra/docker-compose.yml exec api python -c "from app.ingest.pipeline import reindex_embeddings; print(reindex_embeddings())"
```

A first answer can take half a minute on an 8B model. vLLM and llama.cpp use the same variables with their own base URL and model id.

### Cloud chat models

Chat and embeddings are separate. Point chat at Gemini, ChatGPT, or Claude and leave embeddings on local `all-minilm`. Search keeps working, and you do not re-embed the library. There is no separate provider class: the model id's prefix tells LiteLLM which vendor to call, and `LLM_API_KEY` is that vendor's secret. Put the secret in `infra/.env` only.

Leave `LLM_API_BASE` empty. An empty value is kept. Compose fills the Ollama URL only when the variable is absent, so a blank line matters. A cloud model sent to `host.docker.internal:11434` never reaches the vendor.

Recreate the API and the worker after editing the file. Skip `reindex_embeddings` when the embedding model did not change.

```bash
# OpenAI / ChatGPT. The key is the secret from platform.openai.com.
LLM_PROVIDER=litellm
LLM_MODEL=openai/gpt-4o
LLM_API_BASE=
LLM_API_KEY=sk-replace-me
LLM_API_VERSION=
```

```bash
# Anthropic / Claude. The key is the secret from console.anthropic.com.
LLM_PROVIDER=litellm
LLM_MODEL=anthropic/claude-sonnet-4-5
LLM_API_BASE=
LLM_API_KEY=sk-ant-replace-me
```

```bash
# Google AI Studio / Gemini. The key is the secret from aistudio.google.com.
LLM_PROVIDER=litellm
LLM_MODEL=gemini/gemini-2.5-flash
LLM_API_BASE=
LLM_API_KEY=replace-me
```

The text after the slash is the vendor's model id. Replace it with the id that vendor currently serves. Azure OpenAI is the same path with a base URL and an API version: `LLM_MODEL=azure/<deployment>`, `LLM_API_BASE=https://<resource>.openai.azure.com`, and `LLM_API_VERSION=2024-10-21`.

```bash
docker compose -f infra/docker-compose.yml up -d --no-deps --force-recreate api worker
```

A hosted embedding model is a different change. This service checks that every vector is 384 numbers and does not ask the vendor for a shorter vector. `text-embedding-3-small` returns 1536 by default, so it will not start against `vector(384)`. Keep `EMBEDDING_MODEL=openai/all-minilm` and `EMBEDDING_API_BASE` on Ollama unless you add a migration for another width.

## Run

```bash
docker compose -f infra/docker-compose.yml up --build
```

| URL | What |
| --- | --- |
| http://localhost:5173 | Technician UI |
| http://localhost:8000/api/v1/docs | OpenAPI |
| http://localhost:8001 | MCP streamable HTTP |
| http://localhost:3000 | Langfuse. Init user `tech@aurelia.example`, password `aurelia-fleet-dev`, when first-boot init succeeds |

Without Docker, start Postgres with pgvector and Redis. The API, the worker, and the tests share one virtual environment at `backend/.venv`, on Python 3.11. Create it with pip or with uv.

pip:

```bash
python3.11 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
```

uv:

```bash
uv venv backend/.venv --python 3.11
uv pip install -r backend/requirements.txt --python backend/.venv
```

Dev tools (Ruff, mypy, pre-commit) use the same environment and `backend/requirements-dev.txt`, which already includes the runtime packages:

```bash
backend/.venv/bin/pip install -r backend/requirements-dev.txt
```

```bash
uv pip install -r backend/requirements-dev.txt --python backend/.venv
```

Then apply migrations and start the API:

```bash
cd backend && ../.venv/bin/alembic upgrade head && cd ..
PYTHONPATH=backend backend/.venv/bin/uvicorn app.main:app --app-dir backend --reload
```

In another shell, from `frontend/`: `npm install` and `npm run dev`. Start the worker with the Celery command in [How Celery runs the ingest task](#how-celery-runs-the-ingest-task). MCP adds `mcp/requirements.txt` into the same environment.

## Tests

```bash
make test
```

That runs only the suites touched by the current change. A Markdown file, image, or other document does not run tests, locally or in CI. Backend changes run pytest. Frontend changes run Vitest. `make test-all` runs every suite. `make eval` prints retrieval metrics on a seeded database.

GitHub Actions and GitLab CI use the same selector. A document-only change does not start the test jobs. CI uses the fake providers.

Pytest's migrated fixture truncates `chunks`, `jobs`, and `documents` in `DATABASE_URL`. Against the Compose database, that deletes the library. Point tests at a separate database, or re-seed after a full backend run.

Before a commit, Ruff checks and formats staged Python. Before a push, Ruff runs again and mypy type-checks. Documents do not trigger either hook. Install the dev requirements with pip or uv as shown above, then run `make hooks` once. The directory must already be a git repository.

## Not finished

- OCR for scanned PDFs.
- Reader, editor, and admin roles. Tenancy exists. Roles are described in `DECISIONS.md` only.
- An embedding dimension other than 384.
- Langfuse's login screen still has to be opened by a person the first time if headless project init is rejected by the image.
