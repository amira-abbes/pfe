"""normalize active admin department index predicate

Revision ID: 20260616_003
Revises: 20260616_002
Create Date: 2026-06-16
"""

from alembic import op
import sqlalchemy as sa

revision = "20260616_003"
down_revision = "20260616_002"
branch_labels = None
depends_on = None


INDEX_NAME = "ux_utilisateurs_active_admin_per_departement"


def upgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="utilisateurs", schema="app")
    op.create_index(
        INDEX_NAME,
        "utilisateurs",
        ["departement_id"],
        unique=True,
        schema="app",
        postgresql_where=sa.text(
            "UPPER(role) = 'ADMIN' AND est_actif IS TRUE AND date_suppression IS NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="utilisateurs", schema="app")
    op.create_index(
        INDEX_NAME,
        "utilisateurs",
        ["departement_id"],
        unique=True,
        schema="app",
        postgresql_where=sa.text(
            "role = 'ADMIN' AND est_actif IS TRUE AND date_suppression IS NULL"
        ),
    )
