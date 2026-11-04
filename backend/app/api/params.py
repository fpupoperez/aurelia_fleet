"""Shared query parameters. Descriptions are copied into the OpenAPI operation."""

from typing import Annotated
from uuid import UUID

from fastapi import Path, Query

LimitQuery = Annotated[
    int,
    Query(
        ge=1,
        le=100,
        description=(
            "Maximum number of documents on this page. Default 50. "
            "data.count is the total number of matches and can be larger than limit."
        ),
        examples=[50],
    ),
]

OffsetQuery = Annotated[
    int,
    Query(
        ge=1,
        description=(
            "1-based page number. Page 1 is the first page. "
            "Follow data.next instead of inventing the next page."
        ),
        examples=[1],
    ),
]

EquipmentModelQuery = Annotated[
    str | None,
    Query(
        alias="equipmentModel",
        min_length=1,
        max_length=120,
        description="When set, only manuals for this equipment model are returned.",
        examples=["HX-200"],
    ),
]

DocumentIdPath = Annotated[
    UUID,
    Path(
        alias="documentId",
        description="documentId returned by upload_document or list_documents.",
        examples=["00000000-0000-0000-0000-0000000000bb"],
    ),
]

JobIdPath = Annotated[
    UUID,
    Path(
        alias="jobId",
        description="jobId returned by upload_document.",
        examples=["00000000-0000-0000-0000-0000000000aa"],
    ),
]
