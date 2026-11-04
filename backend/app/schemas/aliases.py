"""Alias group request and response models."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.auth import SessionAuth
from app.schemas.envelope import ApiErrorBody


class AliasWrite(BaseModel):
    """Words that mean the same feature. At least two, letters and digits only."""

    model_config = ConfigDict(extra="forbid", title="AliasWrite")

    terms: list[str] = Field(
        min_length=2,
        max_length=8,
        description="Equivalent spellings, such as bluetooth and ble. Each word is stored in lower case.",
        examples=[["bluetooth", "ble"]],
    )


class AliasData(BaseModel):
    """One group of spellings that search treats as the same feature."""
    model_config = ConfigDict(populate_by_name=True, title="AliasData")

    alias_id: UUID = Field(alias="aliasId", description="Stable id of this group.")
    terms: list[str] = Field(description="Spellings that search treats as one feature.")


class AliasListData(BaseModel):
    """Every alias group for the tenant."""
    model_config = ConfigDict(title="AliasListData")

    objects: list[AliasData] = Field(description="Alias groups for this tenant.")


class AliasListResponse(BaseModel):
    """Envelope around the alias list."""
    model_config = ConfigDict(title="AliasListResponse")

    session_auth: SessionAuth
    errors: list[ApiErrorBody] = Field(default_factory=list)
    success: bool = Field(examples=[True])
    data: AliasListData


class AliasResponse(BaseModel):
    """Envelope around one alias group."""
    model_config = ConfigDict(title="AliasResponse")

    session_auth: SessionAuth
    errors: list[ApiErrorBody] = Field(default_factory=list)
    success: bool = Field(examples=[True])
    data: AliasData
