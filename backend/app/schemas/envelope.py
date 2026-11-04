"""Response envelope documented for OpenAPI and MCP clients."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.auth import SessionAuth


class ApiErrorBody(BaseModel):
    """One failure. Read msg and change the request before calling the operation again."""

    model_config = ConfigDict(title="ApiError")

    code: int = Field(
        description="HTTP status that also accompanies this error.",
        examples=[400],
    )
    msg: str = Field(
        description="Human-readable reason. This is the text an agent should surface or correct.",
        examples=["Document not found"],
    )


class ErrorResponse(BaseModel):
    """Failure envelope. success is false and data is null.

    Do not look for a top-level detail key.
    """

    model_config = ConfigDict(
        title="ErrorResponse",
        json_schema_extra={
            "examples": [
                {
                    "session_auth": {"tenantId": "aurelia"},
                    "errors": [{"code": 404, "msg": "Job not found"}],
                    "success": False,
                    "data": None,
                }
            ]
        },
    )

    session_auth: SessionAuth = Field(
        default_factory=SessionAuth,
        description="The session_auth of the caller, or an empty object.",
    )
    errors: list[ApiErrorBody] = Field(
        description="At least one error. Use the first msg as the reason the call failed.",
    )
    success: bool = Field(description="Always false for this schema.", examples=[False])
    data: None = Field(default=None, description="Always null when success is false.")


def failure(status_code: int, message: str, session: dict[str, Any]) -> ErrorResponse:
    """Build an unsuccessful envelope. data is null except when the model is down and passages are attached."""
    return ErrorResponse(
        session_auth=SessionAuth.model_validate(session),
        errors=[ApiErrorBody(code=status_code, msg=message)],
        success=False,
        data=None,
    )


_ERROR_TEXT = {
    400: "The request was rejected. Read errors[0].msg and correct the arguments before retrying.",
    401: (
        "Missing or invalid bearer token. "
        "Send Authorization: Bearer <JWT> and do not retry unchanged."
    ),
    404: "No record with this id is visible to the caller. Do not retry unchanged.",
    409: "The content hash raced with another upload. Read the job again.",
    413: "The file is larger than the configured limit. Send a smaller file.",
    422: (
        "The body, form, or query failed validation. errors[0].msg names the field path "
        "and the reason. The body is this envelope, not a top-level detail array."
    ),
    502: "The model returned a payload that is not the documented answer schema. Safe to retry once.",
    503: (
        "The model provider is unavailable. When data is present it holds the retrieved "
        "passages so the technician can read them. Do not invent an answer."
    ),
    500: "Unexpected failure. The message is generic. Safe to retry once.",
}


def error_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI responses for the shared error envelope."""
    documented: dict[int | str, dict[str, Any]] = {}
    for code in codes:
        documented[code] = {"model": ErrorResponse, "description": _ERROR_TEXT[code]}
    return documented
