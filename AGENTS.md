# Agents

Read this file, then the README of the service you are changing. Do not load every service README up front.

| Change | Read |
| --- | --- |
| HTTP, ingest, retrieval, providers | [backend/README.md](backend/README.md) |
| Celery ingest | [worker/README.md](worker/README.md) |
| UI | [frontend/README.md](frontend/README.md) |
| MCP tools | [mcp/README.md](mcp/README.md) |
| Compose, volumes, ports | [infra/README.md](infra/README.md) |
| Why a number or a refusal exists | [DECISIONS.md](DECISIONS.md) |
| How the system fits together | [README.md](README.md) |

## Do not

- Run the full backend pytest suite against the Compose `DATABASE_URL`. The `migrated` fixture truncates `chunks`, `jobs`, and `documents`. Run the test file you added, or point `DATABASE_URL` at another database.
- Run tests because a Markdown or image file changed. `make test` already skips those.
- Mass-format the tree with Ruff. Format only files you are already editing. The selected rules are E4, E7, E9, and F.
- Change `vector(384)` or `EMBEDDING_DIMENSION` without an Alembic revision and a reindex.
- Add a third model provider. Ollama, vLLM, and hosted APIs are `LLM_PROVIDER=litellm` plus `LLM_API_BASE`. Compose uses that path. Tests force `fake`.
- Put secrets in Compose YAML or READMEs. Compose keys belong in `infra/.env`.
- Treat Langfuse as the language model. It stores traces.

## While editing

- JSON routes return `{session_auth, errors, success, data}`. File download returns bytes.
- `LLM_PROVIDER=fake` returns comparison and word-match answers directly. `litellm` writes the prose from those readings and must not contradict a checked reading.
- Chunks are characters (`CHUNK_SIZE` 800, `CHUNK_OVERLAP` 120) and never cross a page.
- Upload metadata may omit maker, model, and title. A value the caller sent wins over the file.
- Rebuild the Docker image of a service after a code change. The image does not bind-mount the source.
