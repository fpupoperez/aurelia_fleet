# API

FastAPI service in `backend/app`. It accepts manuals, serves the original files, and answers questions. It does not embed on the request thread unless `CELERY_TASK_ALWAYS_EAGER=true` (tests).

## Layout

| Path | Role |
| --- | --- |
| `app/api/v1/` | HTTP routes. JSON envelope except `GET /documents/{id}/file`. |
| `app/services/library.py` | Upload, hash, download confinement, list. |
| `app/services/answers.py` | Ask path: catalog, comparison, search, then chat when the provider is LiteLLM. |
| `app/ingest/` | Extract, column order, chunk, identity (maker, model, title), pipeline. |
| `app/retrieval/` | Hybrid search, maker/model catalog, voltage and temperature readings. |
| `app/providers/` | `fake` and `litellm` only. |
| `app/db/` | SQLAlchemy models. Alembic lives in `backend/migrations`. |
| `tests/` | Pytest. The `migrated` fixture truncates `chunks`, `jobs`, and `documents`. |

Run from `backend/` so Alembic finds `alembic.ini`:

```bash
alembic upgrade head
PYTHONPATH=. uvicorn app.main:app --reload
```

OpenAPI is `/api/v1/docs`. The description in `app/api/openapi.py` is what MCP clients are told to trust.

## Contracts that are easy to break

- Upload metadata is a JSON string field named `metadata`, not a nested file. `equipmentModel`, `maker`, and `title` may be omitted. The file fills them. A typed value wins.
- `original_file` only serves a regular file whose parent is `{data_dir}/uploads`.
- Search filters on `embedding_model`. Do not mix two embedding model names in one query.
- `vector(384)` is fixed until a migration adds another column.
- With `LLM_PROVIDER=fake`, comparison and word-match answers return before the chat provider. With `litellm`, those readings are the evidence and the model writes the prose. Compose sets both providers to `litellm`. The test fixture sets both to `fake`.

Settings and defaults: `app/core/config.py`. The project overview is the repo [README](../README.md).
