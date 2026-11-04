"""Store the equipment maker next to the model."""

from alembic import op

revision = "0002_maker"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE documents ADD COLUMN maker VARCHAR(120) NOT NULL DEFAULT ''")
    op.execute("CREATE INDEX ix_documents_maker ON documents (maker)")
    op.execute(
        """
        UPDATE documents AS document
        SET maker = 'Ruptela'
        WHERE EXISTS (
            SELECT 1 FROM chunks
            WHERE chunks.document_id = document.id
              AND chunks.content ILIKE '%ruptela%'
        )
        """
    )
    op.execute(
        """
        UPDATE documents AS document
        SET maker = 'Aurelia'
        WHERE document.maker = ''
          AND (
            document.equipment_model IN ('HX-200', 'TU-9')
            OR EXISTS (
                SELECT 1 FROM chunks
                WHERE chunks.document_id = document.id
                  AND chunks.content ILIKE '%aurelia%'
            )
          )
        """
    )
    op.execute(
        """
        UPDATE documents AS document
        SET maker = known.maker
        FROM documents AS known
        WHERE document.maker = ''
          AND known.maker <> ''
          AND document.tenant_id = known.tenant_id
          AND document.equipment_model = known.equipment_model
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_documents_maker")
    op.execute("ALTER TABLE documents DROP COLUMN maker")
