"""Resolve the caller from the bearer token or the default tenant."""

from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Request

from app.core.config import Settings
from app.core.errors import ApiError


@dataclass
class Caller:
    """The tenant and subject for this request. Uploads and questions are filtered by tenant_id."""
    session: dict[str, Any]

    @property
    def tenant_id(self) -> str:
        """The tenant whose rows this caller may see."""
        tenant = self.session.get("tenantId")
        if isinstance(tenant, str) and tenant:
            return tenant
        return ""


def get_caller(request: Request, settings: Settings) -> Caller:
    """Return the caller. Missing tokens are 401 only when AUTH_REQUIRED is true."""
    if not settings.auth_required:
        return Caller(session={"tenantId": settings.default_tenant})
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise ApiError(
            401,
            "Missing or invalid bearer token. Send Authorization: Bearer <JWT>.",
        )
    token = header.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise ApiError(401, "Missing or invalid bearer token.") from exc
    session = payload.get("session_auth") or payload.get("sessionAuth") or {}
    if not isinstance(session, dict) or not session.get("tenantId"):
        raise ApiError(401, "Token session_auth.tenantId is required.")
    return Caller(session=session)
