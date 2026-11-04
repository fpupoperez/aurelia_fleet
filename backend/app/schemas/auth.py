"""Identity fields echoed on every JSON response."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SessionAuth(BaseModel):
    """Caller identity echoed back on every response.

    Authorization, when enabled, reads the same object from the bearer token.
    tenantId selects which fleet library the call may see.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True, title="SessionAuth")

    user: str | None = Field(
        default=None,
        description="Display name of the caller. Informational only.",
        examples=["ada"],
    )
    email: str | None = Field(
        default=None,
        description="Email of the caller. Informational only.",
        examples=["ada@aurelia.example"],
    )
    user_id: str | None = Field(
        default=None,
        alias="userId",
        description="Stable user id from the access token.",
        examples=["user-1"],
    )
    tenant_id: str | None = Field(
        default=None,
        alias="tenantId",
        description=(
            "Fleet tenant this call is scoped to. Documents of other tenants are hidden. "
            "When AUTH_REQUIRED is false the API uses the configured default tenant."
        ),
        examples=["aurelia"],
    )

    def dumped(self) -> dict[str, Any]:
        """Return only the fields the caller actually sent."""
        return self.model_dump(mode="json", by_alias=True, exclude_unset=True)
