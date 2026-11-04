"""Initial manuals, jobs, and pgvector chunks."""

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE documents (
            id UUID PRIMARY KEY,
            tenant_id VARCHAR(120) NOT NULL,
            content_hash VARCHAR(64) NOT NULL,
            filename VARCHAR(250) NOT NULL,
            media_type VARCHAR(120) NOT NULL,
            title VARCHAR(250) NOT NULL,
            equipment_model VARCHAR(120) NOT NULL,
            language VARCHAR(16),
            storage_path TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_documents_tenant_hash UNIQUE (tenant_id, content_hash)
        )
        """
    )
    op.execute("CREATE INDEX ix_documents_tenant_id ON documents (tenant_id)")
    op.execute("CREATE INDEX ix_documents_equipment_model ON documents (equipment_model)")
    op.execute(
        """
        CREATE TABLE jobs (
            id UUID PRIMARY KEY,
            document_id UUID NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
            tenant_id VARCHAR(120) NOT NULL,
            status VARCHAR(20) NOT NULL,
            failure_reason TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_jobs_document_id ON jobs (document_id)")
    op.execute("CREATE INDEX ix_jobs_tenant_id ON jobs (tenant_id)")
    op.execute(
        """
        CREATE TABLE chunks (
            id UUID PRIMARY KEY,
            document_id UUID NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
            tenant_id VARCHAR(120) NOT NULL,
            chunk_index INTEGER NOT NULL,
            equipment_model VARCHAR(120) NOT NULL,
            page INTEGER NOT NULL,
            content TEXT NOT NULL,
            tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED,
            embedding vector(384) NOT NULL,
            embedding_model VARCHAR(200) NOT NULL,
            embedding_dim INTEGER NOT NULL,
            CONSTRAINT uq_chunks_document_index UNIQUE (document_id, chunk_index)
        )
        """
    )
    op.execute("CREATE INDEX ix_chunks_document_id ON chunks (document_id)")
    op.execute("CREATE INDEX ix_chunks_tenant_id ON chunks (tenant_id)")
    op.execute("CREATE INDEX ix_chunks_equipment_model ON chunks (equipment_model)")
    op.execute("CREATE INDEX chunks_tsv_gin ON chunks USING gin (tsv)")
    op.execute(
        "CREATE INDEX chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS chunks")
    op.execute("DROP TABLE IF EXISTS jobs")
    op.execute("DROP TABLE IF EXISTS documents")
