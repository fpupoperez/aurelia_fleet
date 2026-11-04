"""Document and job request and response models."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.auth import SessionAuth
from app.schemas.envelope import ApiErrorBody


class JobStatus(StrEnum):
    """Ingest state a client can poll."""

    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class DocumentUploadRequest(BaseModel):
    """JSON metadata sent as the multipart field named metadata."""

    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        title="DocumentUploadRequest",
        json_schema_extra={
            "examples": [
                {
                    "equipmentModel": "HX-200",
                    "maker": "Aurelia",
                    "title": "HX-200 brake service",
                    "language": "en",
                }
            ]
        },
    )

    equipment_model: str = Field(
        default="",
        alias="equipmentModel",
        max_length=120,
        description="Equipment model this manual applies to. Leave it empty to use the model named in the file.",
        examples=["HX-200"],
    )
    maker: str | None = Field(
        default=None,
        max_length=120,
        description="Manufacturer. Stored for fast model and maker lookups. Ingest fills it when the manual names one.",
        examples=["Aurelia"],
    )
    title: str = Field(
        default="",
        max_length=250,
        description="Display title stored with the document and shown on citations. Leave it empty to use the title named in the file.",
        examples=["HX-200 brake service"],
    )
    language: str | None = Field(
        default=None,
        max_length=16,
        description="Optional BCP 47 language tag. Informational. Search uses the simple text config.",
        examples=["en"],
    )


class UploadData(BaseModel):
    """Identifiers returned after an upload is accepted."""

    model_config = ConfigDict(populate_by_name=True, title="UploadData")

    job_id: UUID = Field(
        alias="jobId",
        description="Poll get_job with this id until status is completed or failed.",
        examples=["00000000-0000-0000-0000-0000000000aa"],
    )
    document_id: UUID = Field(
        alias="documentId",
        description="Stable id of the stored manual. Reused when the same bytes are uploaded again.",
        examples=["00000000-0000-0000-0000-0000000000bb"],
    )
    duplicate: bool = Field(
        description=(
            "True when this tenant already stored the same bytes. "
            "The existing job is returned and a second ingest is not queued."
        ),
        examples=[False],
    )


class UploadResponse(BaseModel):
    """Envelope around the job created by an upload."""
    model_config = ConfigDict(title="UploadResponse")

    session_auth: SessionAuth = Field(description="Caller identity for this call.")
    errors: list[ApiErrorBody] = Field(default_factory=list, description="Empty when success is true.")
    success: bool = Field(description="True when the upload was accepted.", examples=[True])
    data: UploadData = Field(description="Job and document ids.")


class JobData(BaseModel):
    """One ingest job."""

    model_config = ConfigDict(populate_by_name=True, title="JobData")

    job_id: UUID = Field(alias="jobId", description="Id returned by upload_document.")
    document_id: UUID = Field(alias="documentId", description="Manual this job processes.")
    status: JobStatus = Field(description="pending, processing, completed, or failed.")
    failure_reason: str | None = Field(
        default=None,
        alias="failureReason",
        description="Why the job failed. Null unless status is failed.",
        examples=[None],
    )
    title: str = Field(description="Document title.")
    equipment_model: str = Field(alias="equipmentModel", description="Equipment model of the document.")
    maker: str = Field(default="", description="Manufacturer. Empty when the manual does not name one.")
    created_at: datetime = Field(alias="createdAt", description="When the job was created, UTC.")
    updated_at: datetime = Field(alias="updatedAt", description="When the job last changed, UTC.")


class JobResponse(BaseModel):
    """Envelope around one job and its document."""
    model_config = ConfigDict(title="JobResponse")

    session_auth: SessionAuth
    errors: list[ApiErrorBody] = Field(default_factory=list)
    success: bool = Field(examples=[True])
    data: JobData


class DocumentData(BaseModel):
    """One manual visible to the caller."""

    model_config = ConfigDict(populate_by_name=True, title="DocumentData")

    document_id: UUID = Field(alias="documentId", description="Stable document id.")
    title: str = Field(description="Display title.")
    equipment_model: str = Field(alias="equipmentModel", description="Equipment model.")
    maker: str = Field(default="", description="Manufacturer. Empty when the manual does not name one.")
    filename: str = Field(description="Original file name.")
    media_type: str = Field(alias="mediaType", description="Stored content type.")
    language: str | None = Field(default=None, description="Language tag when one was stored.")
    chunk_count: int = Field(alias="chunkCount", description="Indexed passages. Zero until ingest finishes.")
    page_count: int = Field(alias="pageCount", description="Distinct pages that produced a passage.")
    status: JobStatus = Field(description="Status of the latest ingest job.")
    failure_reason: str | None = Field(
        default=None,
        alias="failureReason",
        description="Failure reason of the latest job, when status is failed.",
    )
    created_at: datetime = Field(alias="createdAt", description="When the document was stored, UTC.")


class DocumentPage(BaseModel):
    """One page of documents. count is the full match size."""

    model_config = ConfigDict(title="DocumentPage")

    next: str | None = Field(
        description="Query string of the next page, including the leading ?. Null on the last page.",
        examples=["?limit=50&offset=2"],
    )
    count: int = Field(description="Number of documents that match, including other pages.", examples=[1])
    objects: list[DocumentData] = Field(description="Documents on this page.")


class MakerListData(BaseModel):
    """Maker names that match a prefix, for the upload form."""
    model_config = ConfigDict(title="MakerListData")

    objects: list[str] = Field(description="Distinct makers already stored for this tenant.")


class MakerListResponse(BaseModel):
    """Envelope around a maker list."""
    model_config = ConfigDict(title="MakerListResponse")

    session_auth: SessionAuth
    errors: list[ApiErrorBody] = Field(default_factory=list)
    success: bool = Field(examples=[True])
    data: MakerListData


class IdentityData(BaseModel):
    """Names read from a manual before it is stored."""

    model_config = ConfigDict(populate_by_name=True, title="IdentityData")

    equipment_model: str = Field(alias="equipmentModel", description="Model named by the file. Empty when none was found.")
    maker: str = Field(description="Manufacturer named by the file. Empty when none was found.")
    title: str = Field(description="Title suggested from the file. Empty when none was found.")
    language: str | None = Field(default=None, description="Language tag read from the file name, when one is present.")


class IdentityResponse(BaseModel):
    """Envelope around the names read from a file before it is stored."""
    model_config = ConfigDict(title="IdentityResponse")

    session_auth: SessionAuth
    errors: list[ApiErrorBody] = Field(default_factory=list)
    success: bool = Field(examples=[True])
    data: IdentityData


class DocumentListResponse(BaseModel):
    """Envelope around one page of the library."""
    model_config = ConfigDict(title="DocumentListResponse")

    session_auth: SessionAuth
    errors: list[ApiErrorBody] = Field(default_factory=list)
    success: bool = Field(examples=[True])
    data: DocumentPage
