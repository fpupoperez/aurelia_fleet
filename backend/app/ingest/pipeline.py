"""Ingest one job: extract, chunk, embed, store.

A completed job is a no-op, so a duplicate Celery delivery does not embed twice.
A retry deletes that document's chunks and writes a fresh set.
Permanent failures (no text layer, empty file) are stored on the job.
Anything else is raised as a transient error so Celery can retry.
"""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from opentelemetry.trace import Status, StatusCode
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.logging import job_id_var
from app.core.telemetry import record_chunks, record_job, span
from app.db.models import ChunkRow, DocumentRow, JobRow
from app.db.session import session_scope
from app.domain.errors import PermanentIngestError, TransientIngestError
from app.ingest.chunking import chunk_pages
from app.ingest.columns import grounded
from app.ingest.extract import PageText, extract_document
from app.retrieval.catalog import detect_maker
from app.providers import (
    SYSTEM_PROMPT,
    EmbeddingProvider,
    active_embedding_model,
    build_chat_provider,
    build_embedding_provider,
    call_with_retries,
)

logger = logging.getLogger(__name__)


def run_ingest(job_id: str, settings: Settings | None = None) -> None:
    """Process one upload. The job id is attached to logs for the duration of the call."""
    resolved = settings or get_settings()
    token = job_id_var.set(job_id)
    try:
        with session_scope() as session:
            _run(session, UUID(job_id), resolved)
    finally:
        job_id_var.reset(token)


def _run(session: Session, job_id: UUID, settings: Settings) -> None:
    """Move the job from pending to processing, then to completed or failed."""
    job = session.get(JobRow, job_id)
    if job is None:
        logger.warning("Ingest job is missing")
        return
    with span("ingest", job_id=str(job.id), document_id=str(job.document_id), tenant_id=job.tenant_id) as root:
        if job.status == "completed":
            root.add_event("already_completed")
            logger.info("Skipping completed job")
            return
        document = session.get(DocumentRow, job.document_id)
        if document is None:
            _fail(session, job, "The document for this job is missing.")
            return
        job.status = "processing"
        job.failure_reason = None
        session.commit()
        try:
            pages = _extract(document)
            pages = _reading_order(pages, settings)
            if not document.maker:
                document.maker = detect_maker(document.title, document.equipment_model, "\n".join(page.text for page in pages))
            drafts = _chunk(pages, settings)
            if not drafts:
                raise PermanentIngestError("The document has no extractable text.")
            embedder = build_embedding_provider(settings)
            vectors = _embed(drafts, embedder, job, document)
            _store(session, document, drafts, vectors, embedder)
        except PermanentIngestError as exc:
            _fail(session, job, exc.message)
            root.set_status(Status(StatusCode.ERROR, exc.message))
            root.set_attribute("failure_reason", exc.message)
            return
        except TransientIngestError:
            raise
        except Exception as exc:
            logger.exception("Ingest failed with a retryable error")
            raise TransientIngestError(str(exc)) from exc
        job.status = "completed"
        job.failure_reason = None
        session.commit()
        record_job("completed")
        logger.info("Ingest completed")


def _extract(document: DocumentRow) -> list[PageText]:
    """Read the stored file. A PDF with pages but no text layer fails the job. OCR is not used."""
    with span(
        "ingest.extract",
        document_id=str(document.id),
        tenant_id=document.tenant_id,
        equipment_model=document.equipment_model,
    ) as current:
        pages = extract_document(document.storage_path, document.media_type)
        text_pages = [page for page in pages if page.text.strip()]
        current.set_attribute("page_count", len(pages))
        if pages and not text_pages:
            raise PermanentIngestError(
                "The document has no text layer. Scanned pages need OCR, which is not enabled."
            )
        return pages


def _reading_order(pages: list[PageText], settings: Settings) -> list[PageText]:
    """Optionally ask the chat model to reorder a multi-column page.

    The geometric text is kept unless every word in the model's text already appeared in the blocks.
    A model that invents a torque value is discarded.
    """
    if settings.pdf_reading_order != "llm":
        return pages
    chat = build_chat_provider(settings)
    updated: list[PageText] = []
    for page in pages:
        if not page.multi_column or not page.text.strip():
            updated.append(page)
            continue
        with span("ingest.reading_order", page_count=page.page) as current:
            user = (
                "Reorder these text blocks into reading order. Do not add or remove facts.\n"
                f"{page.source}"
            )
            try:
                completion = call_with_retries(chat, system=SYSTEM_PROMPT, user=user, settings=settings)
            except Exception as exc:
                current.add_event("reading_order_skipped", {"reason": str(exc)})
                updated.append(page)
                continue
            if grounded(page.source, completion.text):
                updated.append(PageText(page.page, completion.text, True, page.source))
            else:
                current.add_event("reading_order_rejected")
                logger.info("Rejected a reading-order result that added words")
                updated.append(page)
    return updated


def _chunk(pages: list[PageText], settings: Settings):
    """Pack pages into 800-character windows with overlap, never crossing a page."""
    with span("ingest.chunk") as current:
        drafts = chunk_pages(
            [(page.page, page.text) for page in pages],
            size=settings.chunk_size,
            overlap=settings.chunk_overlap,
        )
        current.set_attribute("chunk_count", len(drafts))
        return drafts


def _embed(drafts, embedder: EmbeddingProvider, job: JobRow, document: DocumentRow):
    """Embed the drafts. A provider error is transient so the worker retries."""
    with span(
        "ingest.embed",
        job_id=str(job.id),
        document_id=str(document.id),
        tenant_id=document.tenant_id,
        equipment_model=document.equipment_model,
        chunk_count=len(drafts),
        embedding_model=embedder.model_name,
        embedding_dim=embedder.dimension,
    ):
        try:
            vectors = _embed_texts(embedder, [draft.content for draft in drafts])
        except Exception as exc:
            raise TransientIngestError(f"Embedding failed: {exc}") from exc
        record_chunks(len(drafts))
        return vectors


def _store(session: Session, document: DocumentRow, drafts, vectors, embedder: EmbeddingProvider) -> None:
    """Replace this document's chunks. The embedding model name is stored so search can filter on it."""
    with span(
        "ingest.upsert",
        document_id=str(document.id),
        tenant_id=document.tenant_id,
        chunk_count=len(drafts),
        embedding_model=embedder.model_name,
        embedding_dim=embedder.dimension,
    ):
        session.execute(delete(ChunkRow).where(ChunkRow.document_id == document.id))
        for draft, vector in zip(drafts, vectors, strict=True):
            session.add(
                ChunkRow(
                    document_id=document.id,
                    tenant_id=document.tenant_id,
                    chunk_index=draft.index,
                    equipment_model=document.equipment_model,
                    page=draft.page,
                    content=draft.content,
                    embedding=vector,
                    embedding_model=embedder.model_name,
                    embedding_dim=embedder.dimension,
                )
            )
        session.commit()


def _fail(session: Session, job: JobRow, reason: str) -> None:
    """Store a permanent failure. The worker does not retry after this."""
    job.status = "failed"
    job.failure_reason = reason
    session.commit()
    record_job("failed")
    logger.info("Ingest failed permanently: %s", reason)


def reindex_embeddings(settings: Settings | None = None) -> int:
    """Re-embed chunks whose model name is not the active one. Dimension stays the column size."""
    resolved = settings or get_settings()
    embedder = build_embedding_provider(resolved)
    target = active_embedding_model(resolved)
    updated = 0
    with session_scope() as session:
        rows = session.scalars(select(ChunkRow).where(ChunkRow.embedding_model != target)).all()
        for start in range(0, len(rows), _EMBED_BATCH):
            batch = rows[start : start + _EMBED_BATCH]
            vectors = _embed_texts(embedder, [row.content for row in batch])
            for row, vector in zip(batch, vectors, strict=True):
                row.embedding = vector
                row.embedding_model = embedder.model_name
                row.embedding_dim = embedder.dimension
                updated += 1
            session.commit()
    return updated


_EMBED_BATCH = 16


def _embed_texts(embedder: EmbeddingProvider, texts: list[str]) -> list[list[float]]:
    """Embed in small batches so a long manual does not send one huge request to Ollama."""
    vectors: list[list[float]] = []
    for start in range(0, len(texts), _EMBED_BATCH):
        vectors.extend(embedder.embed(texts[start : start + _EMBED_BATCH]))
    return vectors


def mark_job_failed(job_id: str, reason: str) -> None:
    """Record the reason after Celery has used its retries. A completed job is left alone."""
    with session_scope() as session:
        job = session.get(JobRow, UUID(job_id))
        if job is None or job.status == "completed":
            return
        job.status = "failed"
        job.failure_reason = reason
    record_job("failed")


def stored_file(settings: Settings, digest: str, filename: str) -> Path:
    """Path of the original bytes: ``{data_dir}/uploads/{sha256}{suffix}``. The original name is not in the path."""
    directory = Path(settings.data_dir) / "uploads"
    directory.mkdir(parents=True, exist_ok=True)
    suffix = Path(filename).suffix.lower()
    return directory / f"{digest}{suffix}"
