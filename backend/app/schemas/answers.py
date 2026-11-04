"""Ask request and the structured answer."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.auth import SessionAuth
from app.schemas.envelope import ApiErrorBody


class Confidence(StrEnum):
    """How strongly the answer is supported by the retrieved passages."""

    high = "high"
    medium = "medium"
    low = "low"
    none = "none"


class AskRequest(BaseModel):
    """One natural-language question against the manual library."""

    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        title="AskRequest",
        json_schema_extra={
            "examples": [
                {
                    "question": "What is the minimum brake pad thickness on the HX-200?",
                    "equipmentModel": "HX-200",
                    "k": 5,
                }
            ]
        },
    )

    question: str = Field(
        min_length=3,
        max_length=2000,
        description="Question in natural language. The service answers only from retrieved manuals.",
        examples=["What is the minimum brake pad thickness on the HX-200?"],
    )
    equipment_model: str | None = Field(
        default=None,
        alias="equipmentModel",
        min_length=1,
        max_length=120,
        description=(
            "When set, retrieval is limited to manuals for this equipment model. "
            "Omit it to search the whole tenant library."
        ),
        examples=["HX-200"],
    )
    k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of passages to retrieve and cite. Default 5.",
        examples=[5],
    )


class Citation(BaseModel):
    """One passage the answer is allowed to use."""

    model_config = ConfigDict(populate_by_name=True, title="Citation")

    chunk_id: UUID = Field(alias="chunkId", description="Id of the stored fragment.")
    document_id: UUID = Field(alias="documentId", description="Manual the fragment comes from.")
    title: str = Field(description="Document title.")
    equipment_model: str = Field(alias="equipmentModel", description="Equipment model of the manual.")
    page: int = Field(description="Page number. For Markdown this is the section index starting at 1.")
    excerpt: str = Field(description="The fragment text.")


class LlmCitation(BaseModel):
    """Citation object the model is allowed to emit. Unknown chunk ids are dropped."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore", title="LlmCitation")

    chunk_id: UUID = Field(alias="chunkId")
    excerpt: str = ""


class LlmAnswer(BaseModel):
    """Structured payload required from the chat provider."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore", title="LlmAnswer")

    answered: bool = Field(description="False when the model refuses for lack of evidence.")
    answer: str = Field(description="The prose answer, or a short refusal.")
    citations: list[LlmCitation] = Field(default_factory=list)
    confidence: Confidence
    refusal_reason: str | None = Field(default=None, alias="refusalReason")


class AnswerData(BaseModel):
    """Answer shown to the technician."""

    model_config = ConfigDict(populate_by_name=True, title="AnswerData")

    answered: bool = Field(
        description="False when the system refuses. Read refusalReason and do not treat answer as a fact.",
        examples=[True],
    )
    answer: str = Field(description="Prose answer, or the refusal sentence.", examples=["The minimum thickness is 4.2 mm."])
    citations: list[Citation] = Field(
        description="Passages used, or the passages retrieved when the model is unavailable.",
    )
    confidence: Confidence = Field(description="high, medium, low, or none.")
    refusal_reason: str | None = Field(
        default=None,
        alias="refusalReason",
        description="Why the system did not answer. Null when answered is true.",
        examples=[None],
    )


class AnswerResponse(BaseModel):
    """Envelope around an answer, a refusal, or the passages returned when the model is down."""
    model_config = ConfigDict(title="AnswerResponse")

    session_auth: SessionAuth
    errors: list[ApiErrorBody] = Field(default_factory=list)
    success: bool = Field(examples=[True])
    data: AnswerData


class UnavailableAnswerResponse(BaseModel):
    """503 body. success is false and data still carries the retrieved passages."""

    model_config = ConfigDict(title="UnavailableAnswerResponse")

    session_auth: SessionAuth
    errors: list[ApiErrorBody]
    success: bool = Field(examples=[False])
    data: AnswerData
