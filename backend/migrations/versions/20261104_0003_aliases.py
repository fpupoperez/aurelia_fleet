"""Store equivalent feature spellings, such as Bluetooth and BLE."""

from alembic import op

revision = "0003_aliases"
down_revision = "0002_maker"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE alias_groups (
            id UUID PRIMARY KEY,
            tenant_id VARCHAR(120) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_alias_groups_tenant_id ON alias_groups (tenant_id)")
    op.execute(
        """
        CREATE TABLE alias_terms (
            id UUID PRIMARY KEY,
            group_id UUID NOT NULL REFERENCES alias_groups (id) ON DELETE CASCADE,
            tenant_id VARCHAR(120) NOT NULL,
            term VARCHAR(40) NOT NULL,
            CONSTRAINT uq_alias_terms_tenant_term UNIQUE (tenant_id, term)
        )
        """
    )
    op.execute("CREATE INDEX ix_alias_terms_group_id ON alias_terms (group_id)")
    op.execute(
        """
        INSERT INTO alias_groups (id, tenant_id)
        VALUES ('00000000-0000-0000-0000-0000000000a1', 'aurelia')
        """
    )
    op.execute(
        """
        INSERT INTO alias_terms (id, group_id, tenant_id, term) VALUES
            ('00000000-0000-0000-0000-0000000000a2', '00000000-0000-0000-0000-0000000000a1', 'aurelia', 'bluetooth'),
            ('00000000-0000-0000-0000-0000000000a3', '00000000-0000-0000-0000-0000000000a1', 'aurelia', 'ble')
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS alias_terms")
    op.execute("DROP TABLE IF EXISTS alias_groups")
