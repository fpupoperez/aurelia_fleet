"""Application settings loaded from the environment."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Runtime configuration. Environment names are the uppercase field names."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    log_level: str = Field(default="INFO", description="Logging level name.")
    process_name: str = Field(default="Aurelia.Fleet", description="Name recorded on logs.")
    app_name: str = Field(default="Aurelia Fleet API", description="OpenAPI title.")
    api_prefix: str = Field(default="/api/v1", description="Path prefix for every route.")
    cors_origin_regex: str = Field(
        default=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
        description="Browser origins allowed to call the API.",
    )
    auth_required: bool = Field(
        default=False,
        description="When true, routes require Authorization: Bearer <JWT>.",
    )
    jwt_secret: str = Field(
        default="dev-only-not-a-production-secret",
        description="HS256 secret used to verify access tokens.",
    )
    default_tenant: str = Field(
        default="aurelia",
        description="Tenant used when AUTH_REQUIRED is false.",
    )
    database_url: str = Field(
        default="postgresql+psycopg://aurelia:aurelia@localhost:5432/aurelia",
        description="SQLAlchemy URL for PostgreSQL with pgvector.",
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis URL used as the Celery broker.",
    )
    celery_task_always_eager: bool = Field(
        default=False,
        description="When true, ingest runs in the API process. Used by tests.",
    )
    data_dir: Path = Field(
        default=_REPO_ROOT / "data",
        description="Directory where uploaded bytes are stored.",
    )
    corpus_dir: Path = Field(
        default=_REPO_ROOT / "corpus",
        description="Sample manuals loaded when the library is empty.",
    )
    evaluation_path: Path = Field(
        default=_REPO_ROOT / "evaluation" / "questions.json",
        description="Retrieval evaluation questions.",
    )
    seed_corpus: bool = Field(
        default=True,
        description="Load the sample corpus on startup when the tenant library is empty.",
    )
    max_upload_bytes: int = Field(default=15 * 1024 * 1024, ge=1)
    chunk_size: int = Field(default=800, ge=200)
    chunk_overlap: int = Field(default=120, ge=0)
    embedding_provider: str = Field(default="fake", description="fake or litellm.")
    embedding_model: str = Field(default="text-embedding-3-small")
    embedding_api_base: str | None = Field(default=None)
    embedding_api_key: str | None = Field(default=None)
    embedding_api_version: str | None = Field(default=None)
    embedding_dimension: int = Field(default=384, ge=8)
    vector_dimension: int = Field(
        default=384,
        description="Dimension of the pgvector column. Changing it needs a migration.",
    )
    llm_provider: str = Field(default="fake", description="fake or litellm.")
    llm_model: str = Field(default="gpt-4o-mini")
    llm_api_base: str | None = Field(default=None)
    llm_api_key: str | None = Field(default=None)
    llm_api_version: str | None = Field(default=None)
    llm_timeout_seconds: float = Field(default=30, gt=0)
    llm_max_attempts: int = Field(default=3, ge=1, description="First try plus retries.")
    llm_retry_backoff_seconds: float = Field(default=0.5, ge=0)
    pdf_reading_order: str = Field(default="geometry", description="geometry or llm.")
    retrieval_k_default: int = Field(default=5, ge=1)
    retrieval_candidates: int = Field(default=20, ge=1)
    max_cosine_distance: float = Field(
        default=0.64,
        ge=0,
        le=2,
        description="Abstain when the nearest chunk is farther than this cosine distance.",
    )
    retrieval_neighbor_margin: float = Field(
        default=0.03,
        ge=0,
        le=0.5,
        description=(
            "Once the nearest chunk is inside the ceiling, also keep chunks within this "
            "extra cosine distance so a broad question can see the rest of the same manual set."
        ),
    )
    min_fused_score: float = Field(
        default=0.01,
        ge=0,
        description="Abstain when the best reciprocal-rank score is below this value.",
    )
    rrf_k: int = Field(default=60, ge=1)
    langfuse_public_key: str | None = Field(default=None)
    langfuse_secret_key: str | None = Field(default=None)
    langfuse_host: str = Field(default="http://localhost:3000")
    otel_service_name: str = Field(default="aurelia-api")

    @field_validator("embedding_provider", "llm_provider", "pdf_reading_order")
    @classmethod
    def _lower(cls, value: str) -> str:
        """Normalize a provider or reading-order name before it is checked."""
        return value.strip().lower()

    @field_validator("embedding_provider", "llm_provider")
    @classmethod
    def _known_provider(cls, value: str) -> str:
        """Allow only fake and litellm. Ollama and hosted APIs are litellm plus a base URL."""
        if value not in {"fake", "litellm"}:
            raise ValueError("provider must be fake or litellm")
        return value

    @field_validator("pdf_reading_order")
    @classmethod
    def _known_order(cls, value: str) -> str:
        """Allow geometry, which is the default, or llm for an optional column reorder."""
        if value not in {"geometry", "llm"}:
            raise ValueError("pdf_reading_order must be geometry or llm")
        return value


@lru_cache
def get_settings() -> Settings:
    """Return the process settings, cached for the lifetime of the process."""
    return Settings()
