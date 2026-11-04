"""Live search of makers already stored in the library."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import Caller, get_request_caller, get_session
from app.schemas.documents import MakerListResponse
from app.schemas.envelope import error_responses
from app.services.library import search_makers, search_models

router = APIRouter(prefix="/makers", tags=["Documents"])
model_router = APIRouter(prefix="/equipment-models", tags=["Documents"])


@router.get(
    "",
    operation_id="list_makers",
    summary="Search makers already stored for this tenant",
    response_model=MakerListResponse,
    responses={
        200: {"model": MakerListResponse, "description": "Matching maker names, in alphabetical order."},
        **error_responses(401, 422, 500),
    },
)
def list_makers_route(
    caller: Annotated[Caller, Depends(get_request_caller)],
    session: Annotated[Session, Depends(get_session)],
    q: Annotated[
        str,
        Query(max_length=120, description="Text typed so far. Empty returns the stored makers."),
    ] = "",
) -> MakerListResponse:
    """Return distinct makers whose names contain q.

    This operation has no JSON body. Use it to fill an upload field with the stored spelling.
    """
    names = search_makers(session, tenant_id=caller.tenant_id, query=q)
    return MakerListResponse.model_validate(
        {
            "session_auth": caller.session,
            "errors": [],
            "success": True,
            "data": {"objects": names},
        }
    )


@model_router.get(
    "",
    operation_id="list_equipment_models",
    summary="Search equipment models already stored for this tenant",
    response_model=MakerListResponse,
    responses={
        200: {"model": MakerListResponse, "description": "Matching equipment models, in alphabetical order."},
        **error_responses(401, 422, 500),
    },
)
def list_equipment_models_route(
    caller: Annotated[Caller, Depends(get_request_caller)],
    session: Annotated[Session, Depends(get_session)],
    q: Annotated[
        str,
        Query(max_length=120, description="Text typed so far. Empty returns the stored equipment models."),
    ] = "",
) -> MakerListResponse:
    """Return distinct equipment models whose names contain q.

    This operation has no JSON body. Use it to fill an upload field with the stored spelling.
    """
    names = search_models(session, tenant_id=caller.tenant_id, query=q)
    return MakerListResponse.model_validate(
        {
            "session_auth": caller.session,
            "errors": [],
            "success": True,
            "data": {"objects": names},
        }
    )
