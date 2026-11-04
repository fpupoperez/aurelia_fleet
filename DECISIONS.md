# Decisions

## Chunking

Manuals are split by structure first, then packed to about 800 characters with 120 characters of overlap. PDF chunks never cross a page, so a citation page is the printed page. Markdown has no printed page, so each heading starts a new section number and that number is stored as the page. Overlap is only inside one page. Empty or unreadable files mark the job failed and do not stay in the queue.

A later embedding model is stored on every chunk (`embedding_model`, `embedding_dim`). Queries filter to the active model, so two models are never mixed in one search. `reindex_embeddings` re-embeds rows whose model name changed, as long as the vector length stays 384. A different length does not fit the `vector(384)` column. That change is a new Alembic revision: add a column, backfill, build an HNSW index, then point search at the new column. The API refuses to start a provider whose configured dimension does not match the column.

## PDF columns

PyMuPDF's plain text stream interleaves columns. The default extractor groups positioned blocks into columns and reads each column from top to bottom. That path is deterministic and is what the tests run.

`PDF_READING_ORDER=llm` sends a multi-column page to the chat provider and keeps the result only when every word already appeared in the extracted blocks. If the model adds a torque value, the geometric text is kept. The model is not the primary reader, because a maintenance answer cannot quote a number the manual did not print. Scanned pages with no text layer fail the job. OCR is not implemented.

## Providers

There are two implementations: `FakeProvider` and `LiteLLMProvider`. Ollama, vLLM, llama.cpp, OpenAI, Azure, Anthropic, and Google are configuration of LiteLLM (`LLM_MODEL`, `LLM_API_BASE`, `LLM_API_KEY`, `LLM_API_VERSION`, and the same `EMBEDDING_*` names). Chat and embeddings can point at different models because those are two settings, not two classes. Tests and the application defaults use `fake`, which hashes tokens into a unit vector and writes a JSON answer from the retrieved sentences. It does not need a key or the network. The Compose stack uses LiteLLM against the host Ollama: `llama3.1:8b` for chat and `all-minilm` for embeddings. `all-minilm` returns 384 values, which matches `vector(384)`. `nomic-embed-text` returns 768 and is not used.

## Hybrid search and refusal

Retrieval is hybrid. pgvector cosine distance and PostgreSQL `tsvector` (`simple`, so part numbers are not stemmed away) are fused with reciprocal rank fusion (`k = 60`). A passage that contains the question's content words is kept even when its cosine distance is past the ceiling. An equipment model, when the caller sends one, is a hard filter. Tenant id is always a hard filter. Each manual also stores a maker. Questions about models or makers are answered from that indexed metadata and do not call the chat model. A question whose words are already in a page is answered from that sentence when `LLM_PROVIDER=fake`. When `LLM_PROVIDER=litellm`, those readings are still selected first, then the chat model writes the prose and must not contradict the checked reading.

The fake embedder is bag-of-words hashing. A short question against a longer chunk often lands near cosine distance 0.55 to 0.63 when the words overlap, and near 0.65 or worse when they do not. The starting ceiling of 0.45 abstained on true questions. The calibrated ceiling is **0.64**: the sample questions sit between about 0.30 and 0.63, and a question about cabin paint (words that are not in the corpus) sits at about 0.65. If the nearest chunk is farther than 0.64, the search abstains and the LLM is not called. When the nearest chunk is inside the ceiling, chunks within **0.03** cosine of that hit are kept as well. A broad question such as "everything about the HX-200" otherwise drops the hydraulics page, which hashes to about 0.65 while the brake page hashes to about 0.64. The fused-score floor is **0.01**, which is about one reciprocal-rank hit. A question that contains a library title or equipment model, or whose only words are part of one, or a caller that already filters by equipment model, stays inside those manuals and does not use the 0.64 ceiling. A question that only names a product returns every page of that manual. If the model still refuses, the answer is the retrieved text. Any question keeps one passage from every manual that contains its content words, including a compound such as "CAN bus" matching "CANbus", even when the hash distance is past 0.64. Wording does not have to be "which devices". Two spellings of one feature count as the same word when they are in the same alias group. A question word of eight letters or more also joins a group when it is one letter off, so "desconnection" finds "disconnection", "desconexiones", and "unplug". Those groups are stored per tenant and edited in the app. Search reads them with one query, and the answer still quotes the manual. A long word has to be present, so "battery" alone does not answer a disconnection question. A question whose words are absent from the library still uses the ceiling. A question that compares a number and a unit, such as "more than 12V" or "more than 60 degrees", is answered from the ranges printed in the manuals. "9–32 V" qualifies because its upper bound is above 12 V. "Do not exceed 12 V" does not. Temperature uses the operating range, including operation without a battery. Storage and charging ranges do not. An upper bound of 60 °C is not more than 60 °C. The comparison stays inside the named maker when the question names one. The hash embedder puts a short product name near distance 0.8 from a long datasheet page even when the page contains that name. The model can still refuse when those excerpts do not contain the requested fact. The evaluation file is the calibration set: three questions that must hit a known sentence and one question whose words are not in any manual, which must abstain. `make test` fails if those scores drop.

## When the model or the queue fails

Upload returns as soon as the job row is stored. A busy broker leaves the job `pending`. Celery retries transient ingest errors twice with exponential backoff (three attempts total) and then stores `failed` with the reason. A duplicate delivery of a completed job does not embed again. Chunks are replaced for that document on a retry, keyed so a redelivery does not duplicate rows.

On the question path the chat provider is called up to three times. If it is still down, the API returns **503** with `success: false` and `data` set to the retrieved passages (`answered: false`, `confidence: none`). The UI shows that the model is unavailable and still lists the passages. A payload that is not the answer schema is retried once and then returned as 502. A refusal because the manuals do not contain the answer is **200** with `answered: false`, not an error.

## Tenancy

Every document and chunk has `tenant_id`. Reads and writes filter on it. With `AUTH_REQUIRED=false` the tenant is `aurelia`, which is the right scope for this prototype. With `AUTH_REQUIRED=true` the tenant comes from `session_auth.tenantId` inside the bearer JWT. A job from another tenant is a 404.

Reader, editor, and admin roles per Aurelia customer are not built. The next step is the same permission list the reference API uses: a role on `tenantId`, editor required to upload, reader required to ask. Row filters already take the tenant, so that change does not reshape the tables.

## Prompt injection

Retrieved text is wrapped in `<untrusted_manual>` markers. The system prompt tells the model that those markers are data, and it includes a canary string the model must not repeat. The fake provider drops sentences that look like instructions and refuses questions that ask for the system prompt. One automated test uploads a manual that says to ignore instructions and reveal the prompt, and asserts the canary is absent and the answer is a refusal.

## Observability

Each process (API, worker, MCP, browser) emits OpenTelemetry. `traceparent` is sent on HTTP calls and on the Celery message. Ingest, retrieval, answer generation, and MCP tools add spans with job id, chunk counts, distances, token counts, and whether the system abstained. The same numbers are histograms and counters. When Langfuse keys are set, those spans are exported to Langfuse. The LiteLLM Python callback is not used: it speaks an older ingestion API than the Langfuse 4 service in Compose. Without keys, export is disabled and the tests use an in-memory span exporter.

Manual text can appear in a real generation's input in Langfuse. File bytes and secrets are not span attributes. Langfuse keys stay on the server. The browser posts OTLP to `/api/v1/otel/v1/traces`, and the API forwards the batch.

## What was used from the directions doc

The tests, and this note from the technical brief and from follow-up decisions about PDF columns, LiteLLM as the only real provider, and Langfuse. The behavior covered by the tests (chunk boundaries, column order, refusal, idempotent upload, retrieval scores) is what should be defended.

## With more time

Add OCR behind the same extractor interface, role checks on top of `tenant_id`, a migration path exercised by a second embedding column, and a Langfuse score written from the evaluation command after each `make eval`.

Taking into account that this solution is aimed to very specific documents with relatively similar information and that follow certain types of information, a probable decistio could be to define an ontology that models and describes the data so the search can be more precise and better structured. Storing that kind of data in a graph database, like Neo4J can be an improvement too, taking advantage of it's node-relations structure and a more LLM-familiar understanding of the data content and distribution.
