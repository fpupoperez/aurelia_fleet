"""Liveness payload."""

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.auth import SessionAuth
from app.schemas.envelope import ApiErrorBody


class StatusData(BaseModel):
    """Process liveness. This operation does not read manuals."""

    model_config = ConfigDict(title="StatusData")

    status: str = Field(description="ok when the process is serving requests.", examples=["ok"])
    process: str = Field(description="Process name from configuration.", examples=["Aurelia.Fleet"])


class StatusResponse(BaseModel):
    """Envelope around the liveness payload."""
    model_config = ConfigDict(title="StatusResponse")

    session_auth: SessionAuth
    errors: list[ApiErrorBody] = Field(default_factory=list)
    success: bool = Field(examples=[True])
    data: StatusData
