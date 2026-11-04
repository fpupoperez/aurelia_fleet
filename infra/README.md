# Compose

`docker-compose.yml` runs Postgres (pgvector 16), Redis, the API, the worker, the frontend, MCP, and Langfuse (its own Postgres, Redis, ClickHouse, and MinIO).

```bash
docker compose -f infra/docker-compose.yml up --build
```

Variable substitution reads `infra/.env`, because that directory is the Compose project directory. Do not commit that file. `.env.example` at the repo root is the template. `LANGFUSE_HOST` inside the API and worker is always `http://langfuse-web:3000` in this file. The browser uses http://localhost:3000.

| Host port | Service |
| --- | --- |
| 5173 | Frontend preview |
| 8000 | API |
| 8001 | MCP |
| 5432 | App Postgres |
| 3000 | Langfuse |

Uploads are the named volume `aurelia_uploads`, mounted at `/app/data` on the API and the worker. They are not in the repo `data/` directory. Deleting the volume deletes the original files. Truncating `documents` in Postgres leaves the files in the volume and drops them from the library.

Images copy source at build time. A code change needs `--build` for that service. An env change needs `--force-recreate` for that service. Provider and Langfuse keys are environment, not image layers.

The API and the worker call LiteLLM whenever a model is required. The default chat model is host Ollama `llama3.1:8b`. Embeddings are `all-minilm` (384 dimensions). A cloud chat model is an `LLM_MODEL` prefix plus `LLM_API_KEY` in `infra/.env`, with `LLM_API_BASE` left empty. See the root README. PDF reading stays geometric unless `PDF_READING_ORDER=llm`. Tests do not use these defaults. They set both providers to `fake`. After switching the embedding model, run `reindex_embeddings` inside the API container so existing chunks match the new model name. Changing only the chat model does not require a reindex.

The API image is `python:3.11`. The frontend image is `node:22` and runs `vite preview`. Langfuse init keys in the compose file are the bootstrap project, separate from keys you create later in the UI and put in `infra/.env`.
