"""Treat unplug detection and desconexión as one feature."""

from alembic import op

revision = "0004_unplug"
down_revision = "0003_aliases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO alias_groups (id, tenant_id)
        SELECT '00000000-0000-0000-0000-0000000000b1', 'aurelia'
        WHERE NOT EXISTS (
            SELECT 1 FROM alias_terms
            WHERE tenant_id = 'aurelia' AND term IN ('unplug', 'disconnection', 'desconexion', 'desconexiones')
        )
        """
    )
    op.execute(
        """
        INSERT INTO alias_terms (id, group_id, tenant_id, term)
        SELECT term_id, '00000000-0000-0000-0000-0000000000b1', 'aurelia', term
        FROM (VALUES
            ('00000000-0000-0000-0000-0000000000b2'::uuid, 'unplug'),
            ('00000000-0000-0000-0000-0000000000b3'::uuid, 'disconnection'),
            ('00000000-0000-0000-0000-0000000000b4'::uuid, 'desconexion'),
            ('00000000-0000-0000-0000-0000000000b5'::uuid, 'desconexiones')
        ) AS seed(term_id, term)
        WHERE EXISTS (
            SELECT 1 FROM alias_groups WHERE id = '00000000-0000-0000-0000-0000000000b1'
        )
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM alias_groups WHERE id = '00000000-0000-0000-0000-0000000000b1'"
    )
