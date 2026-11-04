"""List and edit feature aliases."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.api.deps import Caller, get_request_caller, get_session
from app.core.errors import ApiError
from app.domain.errors import DomainError
from app.schemas.aliases import AliasListResponse, AliasResponse, AliasWrite
from app.schemas.envelope import error_responses
from app.services.aliases import create_alias, delete_alias, list_aliases, update_alias

router = APIRouter(prefix="/aliases", tags=["Aliases"])

AliasIdPath = Annotated[
    UUID,
    Path(alias="aliasId", description="aliasId from list_aliases or create_alias."),
]


def _data(group_id: UUID, terms: list[str]) -> dict:
    """The alias object nested in the envelope."""
    return {"aliasId": str(group_id), "terms": terms}


@router.get(
    "",
    operation_id="list_aliases",
    summary="List feature spellings for this tenant",
    response_model=AliasListResponse,
    responses={200: {"model": AliasListResponse, "description": "Every alias group."}, **error_responses(401, 500)},
)
def list_aliases_route(
    caller: Annotated[Caller, Depends(get_request_caller)],
    session: Annotated[Session, Depends(get_session)],
) -> AliasListResponse:
    """Return the groups search treats as one feature.

    This operation has no JSON body. A group such as bluetooth and ble makes either word find the other.
    """
    groups = list_aliases(session, caller.tenant_id)
    return AliasListResponse.model_validate(
        {
            "session_auth": caller.session,
            "errors": [],
            "success": True,
            "data": {"objects": [_data(group.id, terms) for group, terms in groups]},
        }
    )


@router.post(
    "",
    operation_id="create_alias",
    summary="Add a group of equivalent words",
    status_code=201,
    response_model=AliasResponse,
    responses={
        201: {"model": AliasResponse, "description": "The stored group."},
        **error_responses(400, 401, 409, 422, 500),
    },
)
def create_alias_route(
    body: AliasWrite,
    caller: Annotated[Caller, Depends(get_request_caller)],
    session: Annotated[Session, Depends(get_session)],
) -> AliasResponse:
    """Store a new group. Each word may belong to only one group."""
    try:
        group, terms = create_alias(session, tenant_id=caller.tenant_id, terms=body.terms)
    except DomainError as exc:
        raise ApiError(exc.status_code, exc.message, session=caller.session) from exc
    return AliasResponse.model_validate(
        {"session_auth": caller.session, "errors": [], "success": True, "data": _data(group.id, terms)}
    )


@router.put(
    "/{aliasId}",
    operation_id="update_alias",
    summary="Replace the words in one group",
    response_model=AliasResponse,
    responses={
        200: {"model": AliasResponse, "description": "The updated group."},
        **error_responses(400, 401, 404, 409, 422, 500),
    },
)
def update_alias_route(
    aliasId: AliasIdPath,
    body: AliasWrite,
    caller: Annotated[Caller, Depends(get_request_caller)],
    session: Annotated[Session, Depends(get_session)],
) -> AliasResponse:
    """Replace every word in the group. Send the full list, not a single added word."""
    try:
        group, terms = update_alias(session, tenant_id=caller.tenant_id, alias_id=aliasId, terms=body.terms)
    except DomainError as exc:
        raise ApiError(exc.status_code, exc.message, session=caller.session) from exc
    return AliasResponse.model_validate(
        {"session_auth": caller.session, "errors": [], "success": True, "data": _data(group.id, terms)}
    )


@router.delete(
    "/{aliasId}",
    operation_id="delete_alias",
    summary="Delete one alias group",
    response_model=AliasResponse,
    responses={
        200: {"model": AliasResponse, "description": "The deleted group."},
        **error_responses(401, 404, 422, 500),
    },
)
def delete_alias_route(
    aliasId: AliasIdPath,
    caller: Annotated[Caller, Depends(get_request_caller)],
    session: Annotated[Session, Depends(get_session)],
) -> AliasResponse:
    """Remove a group. Later questions no longer treat those words as the same feature."""
    try:
        group, terms = delete_alias(session, tenant_id=caller.tenant_id, alias_id=aliasId)
    except DomainError as exc:
        raise ApiError(exc.status_code, exc.message, session=caller.session) from exc
    return AliasResponse.model_validate(
        {"session_auth": caller.session, "errors": [], "success": True, "data": _data(group.id, terms)}
    )
