"""Liveness."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.deps import Caller, get_request_caller, get_settings_from_app
from app.core.config import Settings
from app.schemas.envelope import error_responses
from app.schemas.status import StatusResponse

router = APIRouter(prefix="/status", tags=["Status"])


@router.get(
    "",
    operation_id="get_service_status",
    summary="Check that the API process is serving requests",
    response_model=StatusResponse,
    response_model_exclude_unset=True,
    responses={
        200: {"model": StatusResponse, "description": "The process is up. This does not check a manual."},
        **error_responses(500),
    },
)
def get_service_status(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings_from_app)],
    caller: Annotated[Caller, Depends(get_request_caller)],
) -> StatusResponse:
    """Report process liveness.

    This operation has no JSON body. It does not read documents or call a model.
    """
    del request
    return StatusResponse.model_validate(
        {
            "session_auth": caller.session,
            "errors": [],
            "success": True,
            "data": {"status": "ok", "process": settings.process_name},
        }
    )
