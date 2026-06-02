"""allow current user account status values

Revision ID: 20260601_001
Revises: 20260504_001
Create Date: 2026-06-01
"""

from alembic import op

revision = "20260601_001"
down_revision = "20260504_001"
branch_labels = None
depends_on = None


CURRENT_AND_LEGACY_STATUSES = (
    "EN_ATTENTE_PREMIERE_CONNEXION",
    "ACTIF",
    "DESACTIVE_ADMIN",
    "BLOQUE_TENTATIVES",
    "SUPPRIME",
    "PENDING_ACTIVATION",
    "MFA_SETUP_REQUIRED",
    "ACTIVE",
    "DISABLED",
    "DELETED",
)


LEGACY_STATUSES = (
    "PENDING_ACTIVATION",
    "MFA_SETUP_REQUIRED",
    "ACTIVE",
    "DISABLED",
    "DELETED",
)


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE app.utilisateurs
        DROP CONSTRAINT IF EXISTS chk_utilisateurs_statut_compte
        """
    )
    op.execute(
        f"""
        ALTER TABLE app.utilisateurs
        ADD CONSTRAINT chk_utilisateurs_statut_compte
        CHECK (statut_compte IN ({_quoted(CURRENT_AND_LEGACY_STATUSES)}))
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE app.utilisateurs
        DROP CONSTRAINT IF EXISTS chk_utilisateurs_statut_compte
        """
    )
    op.execute(
        f"""
        ALTER TABLE app.utilisateurs
        ADD CONSTRAINT chk_utilisateurs_statut_compte
        CHECK (statut_compte IN ({_quoted(LEGACY_STATUSES)}))
        """
    )
