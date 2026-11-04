---
name: aurelia-fleet
description: >-
  Continue development of the Aurelia Fleet manuals assistant. Use when editing
  this repo's API, worker, retrieval, ingest, frontend, MCP server, Compose
  stack, tests, or docs, or when the user mentions manuals, citations, chunks,
  pgvector, Langfuse, Ollama, or the ask flow.
---

# Aurelia Fleet

## Start

1. Read [AGENTS.md](../../../AGENTS.md).
2. Read the README of the service you will change, and nothing else until the task needs it.
3. Use [DECISIONS.md](../../../DECISIONS.md) for retrieval ceilings, chunk policy, and refusal behavior.

## Change rules

- Match existing names. Do not add a provider other than `fake` or `litellm`.
- A real chat model writes prose from retrieved or checked readings. The fake provider keeps the direct answer. Do not delete that split.
- Page-bounded chunks stay page-bounded. Citation page numbers must remain the printed page or the Markdown section index.
- Tests that need Postgres must not use the Compose database the user is browsing, unless the user asked to reset it.
- Rebuild the affected image after a code change the user will see in Docker.

## Where behavior lives

| Task | File |
| --- | --- |
| Ask order | `backend/app/services/answers.py` |
| Search and typos | `backend/app/retrieval/search.py` |
| Voltage and temperature | `backend/app/retrieval/compare.py` |
| Maker and model questions | `backend/app/retrieval/catalog.py` |
| Upload and download | `backend/app/services/library.py` |
| Names read from a file | `backend/app/ingest/identity.py` |
| Chunk windows | `backend/app/ingest/chunking.py` |
| Which tests run | `scripts/select_tests.py` |
