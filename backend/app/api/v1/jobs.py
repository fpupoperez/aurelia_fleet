"""Job status."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import Caller, get_request_caller, get_session
from app.api.params import JobIdPath
from app.core.errors import ApiError
from app.domain.errors import DomainError
from app.schemas.documents import JobResponse
from app.schemas.envelope import error_responses
from app.services.library import get_job

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get(
    "/{jobId}",
    operation_id="get_job",
    summary="Read the ingest status of one upload",
    response_model=JobResponse,
    response_model_exclude_unset=True,
    responses={
        200: {
            "model": JobResponse,
            "description": "The job. Poll until status is completed or failed.",
        },
        **error_responses(401, 404, 422, 500),
    },
)
def get_job_route(
    jobId: JobIdPath,
    caller: Annotated[Caller, Depends(get_request_caller)],
    session: Annotated[Session, Depends(get_session)],
) -> JobResponse:
    """Return one job for this tenant.

    This operation has no JSON body. A missing job and a job from another tenant are both 404.
    failureReason is null unless status is failed.
    """
    try:
        job, document = get_job(session, tenant_id=caller.tenant_id, job_id=jobId)
    except DomainError as exc:
        raise ApiError(exc.status_code, exc.message, session=caller.session) from exc
    return JobResponse.model_validate(
        {
            "session_auth": caller.session,
            "errors": [],
            "success": True,
            "data": {
                "jobId": str(job.id),
                "documentId": str(document.id),
                "status": job.status,
                "failureReason": job.failure_reason,
                "title": document.title,
                "equipmentModel": document.equipment_model,
                "maker": document.maker,
                "createdAt": job.created_at,
                "updatedAt": job.updated_at,
            },
        }
    )
