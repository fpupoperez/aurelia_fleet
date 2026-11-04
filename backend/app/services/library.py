"""Upload manuals and read job state."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from uuid import UUID

from opentelemetry.propagate import inject
from sqlalchemy import distinct, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import ChunkRow, DocumentRow, JobRow
from app.domain.errors import DomainError
from app.ingest.identity import ManualIdentity, read_identity, resolved_metadata
from app.ingest.pipeline import stored_file
from app.schemas.documents import DocumentUploadRequest

logger = logging.getLogger(__name__)

_ALLOWED = {
    "application/pdf": {".pdf"},
    "text/markdown": {".md", ".markdown"},
    "text/plain": {".txt", ".md", ".markdown"},
}


def classify(filename: str, media_type: str | None) -> str:
    """Accept PDF, Markdown, and plain text. A generic content type falls back to the extension."""
    suffix = _suffix(filename)
    normalized = (media_type or "").split(";")[0].strip().lower()
    by_suffix = _type_from_suffix(suffix)
    if normalized in {"application/octet-stream", ""}:
        normalized = by_suffix
    if normalized == "text/plain" and suffix in {".md", ".markdown"}:
        normalized = "text/markdown"
    allowed_suffixes = _ALLOWED.get(normalized)
    if allowed_suffixes is None or (suffix and suffix not in allowed_suffixes):
        if by_suffix:
            return by_suffix
        raise DomainError(
            "Unsupported file type. Send a PDF, Markdown, or plain text file.",
            status_code=400,
        )
    return normalized


def upload(
    session: Session,
    settings: Settings,
    *,
    tenant_id: str,
    filename: str,
    media_type: str | None,
    raw: bytes,
    metadata: DocumentUploadRequest,
) -> tuple[DocumentRow, JobRow, bool]:
    """Store the bytes by hash, create a job, and enqueue ingest. The same hash returns the existing job."""
    if len(raw) > settings.max_upload_bytes:
        raise DomainError("The file is larger than the 15 MB limit.", status_code=413)
    if not raw:
        raise DomainError("The file is empty.", status_code=400)
    stored_type = classify(filename, media_type)
    identity = read_identity(raw, filename, stored_type)
    equipment_model, maker, title, language = resolved_metadata(metadata, identity)
    digest = hashlib.sha256(raw).hexdigest()
    existing = session.scalar(
        select(DocumentRow).where(
            DocumentRow.tenant_id == tenant_id,
            DocumentRow.content_hash == digest,
        )
    )
    if existing is not None:
        job = _latest_job(session, existing.id)
        if job is None:
            raise DomainError("The stored document has no job.", status_code=500)
        return existing, job, True
    path = stored_file(settings, digest, filename)
    path.write_bytes(raw)
    document = DocumentRow(
        tenant_id=tenant_id,
        content_hash=digest,
        filename=filename[:250] or "upload",
        media_type=stored_type,
        title=title,
        equipment_model=equipment_model,
        maker=maker,
        language=language,
        storage_path=str(path),
    )
    session.add(document)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raced = session.scalar(
            select(DocumentRow).where(
                DocumentRow.tenant_id == tenant_id,
                DocumentRow.content_hash == digest,
            )
        )
        if raced is None:
            raise DomainError("The same file was uploaded at the same time. Read the job again.", status_code=409) from exc
        job = _latest_job(session, raced.id)
        if job is None:
            raise DomainError("The stored document has no job.", status_code=500) from exc
        return raced, job, True
    job = JobRow(document_id=document.id, tenant_id=tenant_id, status="pending")
    session.add(job)
    session.commit()
    _enqueue(settings, job.id)
    session.refresh(document)
    session.refresh(job)
    return document, job, False


def describe(
    settings: Settings,
    *,
    filename: str,
    media_type: str | None,
    raw: bytes,
) -> ManualIdentity:
    """Read maker, model, and title from a file without storing it."""
    if len(raw) > settings.max_upload_bytes:
        raise DomainError("The file is larger than the 15 MB limit.", status_code=413)
    if not raw:
        raise DomainError("The file is empty.", status_code=400)
    stored_type = classify(filename, media_type)
    return read_identity(raw, filename, stored_type)


def original_file(
    session: Session,
    settings: Settings,
    *,
    tenant_id: str,
    document_id: UUID,
) -> tuple[Path, str, str]:
    """Return the stored bytes path, download name, and media type for one tenant document."""
    document = session.get(DocumentRow, document_id)
    if document is None or document.tenant_id != tenant_id:
        raise DomainError("Document not found.", status_code=404)
    path = Path(document.storage_path).resolve()
    root = (Path(settings.data_dir) / "uploads").resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise DomainError("The original file is not available.", status_code=404) from exc
    if path.parent != root or not path.is_file():
        raise DomainError("The original file is not available.", status_code=404)
    return path, document.filename, document.media_type


def get_job(session: Session, *, tenant_id: str, job_id: UUID) -> tuple[JobRow, DocumentRow]:
    """One job and its document, or 404 when the id is unknown or belongs to another tenant."""
    row = session.execute(
        select(JobRow, DocumentRow)
        .join(DocumentRow, DocumentRow.id == JobRow.document_id)
        .where(JobRow.id == job_id, JobRow.tenant_id == tenant_id)
    ).one_or_none()
    if row is None:
        raise DomainError("Job not found.", status_code=404)
    job, document = row
    return job, document


def search_makers(session: Session, *, tenant_id: str, query: str, limit: int = 8) -> list[str]:
    """Maker names already in this tenant, for the upload suggestions."""
    return _search_names(session, DocumentRow.maker, tenant_id=tenant_id, query=query, limit=limit)


def search_models(session: Session, *, tenant_id: str, query: str, limit: int = 20) -> list[str]:
    """Equipment model names already in this tenant."""
    return _search_names(session, DocumentRow.equipment_model, tenant_id=tenant_id, query=query, limit=limit)


def _search_names(session: Session, column, *, tenant_id: str, query: str, limit: int) -> list[str]:
    """Prefix search over one document column, scoped to the tenant."""
    statement = (
        select(column)
        .where(DocumentRow.tenant_id == tenant_id, column != "")
        .distinct()
        .order_by(column)
        .limit(limit)
    )
    cleaned = query.strip()
    if cleaned:
        escaped = cleaned.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        statement = statement.where(column.ilike(f"%{escaped}%", escape="\\"))
    return list(session.scalars(statement))


def list_documents(
    session: Session,
    *,
    tenant_id: str,
    equipment_model: str | None,
    limit: int,
    offset: int,
) -> tuple[list[tuple[DocumentRow, JobRow]], int, dict[UUID, tuple[int, int]]]:
    """One page of manuals with chunk counts and the latest job."""
    filters = [DocumentRow.tenant_id == tenant_id]
    if equipment_model:
        filters.append(DocumentRow.equipment_model == equipment_model)
    total = session.scalar(select(func.count()).select_from(DocumentRow).where(*filters)) or 0
    documents = session.scalars(
        select(DocumentRow)
        .where(*filters)
        .order_by(DocumentRow.created_at.desc())
        .offset((offset - 1) * limit)
        .limit(limit)
    ).all()
    pairs: list[tuple[DocumentRow, JobRow]] = []
    for document in documents:
        job = _latest_job(session, document.id)
        if job is not None:
            pairs.append((document, job))
    return pairs, int(total), _index_stats(session, [document.id for document, _job in pairs])


def _index_stats(session: Session, document_ids: list[UUID]) -> dict[UUID, tuple[int, int]]:
    """How many chunks each document has, and how many distinct pages those chunks cover."""
    if not document_ids:
        return {}
    rows = session.execute(
        select(ChunkRow.document_id, func.count(), func.count(distinct(ChunkRow.page)))
        .where(ChunkRow.document_id.in_(document_ids))
        .group_by(ChunkRow.document_id)
    ).all()
    return {document_id: (int(chunks), int(pages)) for document_id, chunks, pages in rows}


def _latest_job(session: Session, document_id: UUID) -> JobRow | None:
    """The newest ingest job for a document, so the library can show pending or failed."""
    return session.scalar(
        select(JobRow).where(JobRow.document_id == document_id).order_by(JobRow.created_at.desc())
    )


def _enqueue(settings: Settings, job_id: UUID) -> None:
    """Send ingest_document to Celery, carrying the current trace context on the message."""
    if settings.celery_task_always_eager:
        from app.ingest.pipeline import run_ingest

        run_ingest(str(job_id), settings)
        return
    from celery import Celery

    headers: dict[str, str] = {}
    inject(headers)
    client = Celery("aurelia", broker=settings.redis_url)
    client.send_task("ingest_document", args=[str(job_id)], headers=headers)


def _suffix(filename: str) -> str:
    """The lowercase file extension, including the dot."""
    dot = filename.rfind(".")
    if dot == -1:
        return ""
    return filename[dot:].lower()


def _type_from_suffix(suffix: str) -> str:
    """The media type implied by the extension when the browser sent a generic type."""
    if suffix == ".pdf":
        return "application/pdf"
    if suffix in {".md", ".markdown"}:
        return "text/markdown"
    if suffix == ".txt":
        return "text/plain"
    return ""
