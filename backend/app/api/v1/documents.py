"""Upload and list manuals."""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.deps import Caller, get_request_caller, get_session, get_settings_from_app
from app.api.pagination import next_page
from app.api.params import DocumentIdPath, EquipmentModelQuery, LimitQuery, OffsetQuery
from app.core.config import Settings
from app.core.errors import ApiError
from app.domain.errors import DomainError
from app.schemas.documents import DocumentListResponse, DocumentUploadRequest, IdentityResponse, UploadResponse
from app.schemas.envelope import error_responses
from app.services.library import describe, list_documents, original_file, upload

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post(
    "",
    operation_id="upload_document",
    summary="Upload one manual and queue ingest",
    status_code=201,
    response_model=UploadResponse,
    response_model_exclude_unset=True,
    responses={
        201: {
            "model": UploadResponse,
            "description": (
                "The file was accepted. data.jobId is what get_job polls. "
                "data.duplicate is true when these bytes were already stored."
            ),
        },
        **error_responses(400, 401, 409, 413, 422, 500),
    },
)
async def upload_document(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings_from_app)],
    caller: Annotated[Caller, Depends(get_request_caller)],
    session: Annotated[Session, Depends(get_session)],
    file: Annotated[UploadFile, File(description="PDF, Markdown, or plain text manual.")],
    metadata: Annotated[
        str,
        Form(
            description=(
                "JSON object with optional equipmentModel, maker, title, and language. "
                "Omitted names are read from the file. "
                "This is DocumentUploadRequest, sent as a string because the body is multipart."
            ),
            examples=['{"equipmentModel":"HX-200","title":"HX-200 brake service"}'],
        ),
    ],
) -> UploadResponse:
    """Store one manual for the caller's tenant.

    Send multipart form fields file and metadata. metadata is a JSON string, not a nested file.
    The same bytes for the same tenant return the existing job and do not queue ingest again.
    A failed or empty document still returns a job. Read get_job for failureReason.
    """
    del request
    try:
        parsed = DocumentUploadRequest.model_validate(json.loads(metadata))
    except json.JSONDecodeError as exc:
        raise ApiError(422, "metadata: must be a JSON object", session=caller.session) from exc
    except ValidationError as exc:
        parts = []
        for error in exc.errors():
            place = ".".join(str(item) for item in error.get("loc", ()))
            parts.append(f"metadata.{place}: {error.get('msg')}")
        raise ApiError(422, "; ".join(parts) or "metadata is invalid", session=caller.session) from exc
    raw = await file.read()
    if len(raw) > settings.max_upload_bytes:
        raise ApiError(413, "The file is larger than the 15 MB limit.", session=caller.session)
    try:
        document, job, duplicate = upload(
            session,
            settings,
            tenant_id=caller.tenant_id,
            filename=file.filename or "upload.txt",
            media_type=file.content_type,
            raw=raw,
            metadata=parsed,
        )
    except DomainError as exc:
        raise ApiError(exc.status_code, exc.message, session=caller.session) from exc
    return UploadResponse.model_validate(
        {
            "session_auth": caller.session,
            "errors": [],
            "success": True,
            "data": {
                "jobId": str(job.id),
                "documentId": str(document.id),
                "duplicate": duplicate,
            },
        }
    )


@router.post(
    "/identity",
    operation_id="describe_document",
    summary="Read the maker, model, and title printed on a manual",
    response_model=IdentityResponse,
    response_model_exclude_unset=True,
    responses={
        200: {
            "model": IdentityResponse,
            "description": "Names found in the file. Empty strings mean the file did not name that field.",
        },
        **error_responses(400, 401, 413, 422, 500),
    },
)
async def describe_document(
    settings: Annotated[Settings, Depends(get_settings_from_app)],
    caller: Annotated[Caller, Depends(get_request_caller)],
    file: Annotated[UploadFile, File(description="PDF, Markdown, or plain text manual.")],
) -> IdentityResponse:
    """Read maker, model, and title from a file without storing it.

    Send the file as multipart field file. The caller can show these values and change them before upload_document.
    """
    raw = await file.read()
    if len(raw) > settings.max_upload_bytes:
        raise ApiError(413, "The file is larger than the 15 MB limit.", session=caller.session)
    try:
        identity = describe(
            settings,
            filename=file.filename or "upload.txt",
            media_type=file.content_type,
            raw=raw,
        )
    except DomainError as exc:
        raise ApiError(exc.status_code, exc.message, session=caller.session) from exc
    return IdentityResponse.model_validate(
        {
            "session_auth": caller.session,
            "errors": [],
            "success": True,
            "data": {
                "equipmentModel": identity.equipment_model,
                "maker": identity.maker,
                "title": identity.title,
                "language": identity.language,
            },
        }
    )


@router.get(
    "/{documentId}/file",
    operation_id="download_document",
    summary="Download the original manual",
    response_class=FileResponse,
    responses={
        200: {
            "description": (
                "The original file, streamed in 64 KB chunks. "
                "This body is the file itself, not the JSON envelope. "
                "Content-Disposition is attachment and uses the stored filename."
            ),
            "content": {
                "application/pdf": {"schema": {"type": "string", "format": "binary"}},
                "text/markdown": {"schema": {"type": "string", "format": "binary"}},
                "text/plain": {"schema": {"type": "string", "format": "binary"}},
            },
        },
        **error_responses(401, 404, 422, 500),
    },
)
def download_document(
    documentId: DocumentIdPath,
    settings: Annotated[Settings, Depends(get_settings_from_app)],
    caller: Annotated[Caller, Depends(get_request_caller)],
    session: Annotated[Session, Depends(get_session)],
) -> FileResponse:
    """Stream the stored manual for this tenant.

    This operation has no JSON body. A missing document and a document from another tenant are both 404.
    The file is read from disk in chunks and is not loaded into memory as a whole.
    """
    try:
        path, filename, media_type = original_file(
            session,
            settings,
            tenant_id=caller.tenant_id,
            document_id=documentId,
        )
    except DomainError as exc:
        raise ApiError(exc.status_code, exc.message, session=caller.session) from exc
    return FileResponse(
        path,
        media_type=media_type,
        filename=filename,
        content_disposition_type="attachment",
    )


@router.get(
    "",
    operation_id="list_documents",
    summary="List manuals visible to the tenant",
    response_model=DocumentListResponse,
    response_model_exclude_unset=True,
    responses={
        200: {
            "model": DocumentListResponse,
            "description": "One page of manuals. data.count is the total.",
        },
        **error_responses(401, 422, 500),
    },
)
def list_documents_route(
    request: Request,
    caller: Annotated[Caller, Depends(get_request_caller)],
    session: Annotated[Session, Depends(get_session)],
    limit: LimitQuery = 50,
    offset: OffsetQuery = 1,
    equipment_model: EquipmentModelQuery = None,
) -> DocumentListResponse:
    """Return manuals for this tenant.

    This operation has no JSON body. Set equipmentModel to filter. offset starts at 1.
    """
    try:
        pairs, total, stats = list_documents(
            session,
            tenant_id=caller.tenant_id,
            equipment_model=equipment_model,
            limit=limit,
            offset=offset,
        )
    except DomainError as exc:
        raise ApiError(exc.status_code, exc.message, session=caller.session) from exc
    objects = [
        {
            "documentId": str(document.id),
            "title": document.title,
            "equipmentModel": document.equipment_model,
            "maker": document.maker,
            "filename": document.filename,
            "mediaType": document.media_type,
            "language": document.language,
            "chunkCount": stats.get(document.id, (0, 0))[0],
            "pageCount": stats.get(document.id, (0, 0))[1],
            "status": job.status,
            "failureReason": job.failure_reason,
            "createdAt": document.created_at,
        }
        for document, job in pairs
    ]
    return DocumentListResponse.model_validate(
        {
            "session_auth": caller.session,
            "errors": [],
            "success": True,
            "data": {
                "next": next_page(request, offset=offset, limit=limit, total=total),
                "count": total,
                "objects": objects,
            },
        }
    )
