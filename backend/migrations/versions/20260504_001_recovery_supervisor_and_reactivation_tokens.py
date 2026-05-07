"""allow recovery supervisor and reactivation token types

Revision ID: 20260504_001
Revises: 20260429_002
Create Date: 2026-05-04
"""

from alembic import op

revision = "20260504_001"
down_revision = "20260429_002"
branch_labels = None
depends_on = None


RESET_TOKEN_TYPES = (
    "PASSWORD_RESET",
    "PASSWORD_RESET_FROM_LOCKOUT",
    "RESET_PASSWORD_RECOVERY_CODE",
    "SECURITY_REPORT",
    "MFA_BACKUP_CODE",
    "MFA_RESET",
    "MFA_SETUP",
    "RECOVERY_CODE_ASSISTANCE",
    "SUPER_ADMIN_SECURE_RECOVERY_24H",
    "RECOVERY_SUPERVISOR_ACTION",
    "ACCOUNT_REACTIVATION_REQUEST",
)


PREVIOUS_RESET_TOKEN_TYPES = (
    "PASSWORD_RESET",
    "PASSWORD_RESET_FROM_LOCKOUT",
    "RESET_PASSWORD_RECOVERY_CODE",
    "SECURITY_REPORT",
    "MFA_BACKUP_CODE",
    "MFA_RESET",
    "MFA_SETUP",
    "RECOVERY_CODE_ASSISTANCE",
    "SUPER_ADMIN_SECURE_RECOVERY_24H",
)


def _values(items: tuple[str, ...]) -> str:
    return ", ".join(f"'{item}'" for item in items)


def _replace_constraints(values: str) -> None:
    op.execute(
        """
        ALTER TABLE app.jetons_reinitialisation_mot_de_passe
        DROP CONSTRAINT IF EXISTS chk_reset_type_token
        """
    )
    op.execute(
        f"""
        ALTER TABLE app.jetons_reinitialisation_mot_de_passe
        ADD CONSTRAINT chk_reset_type_token
        CHECK (type_token IS NULL OR type_token IN ({values}))
        """
    )
    op.execute(
        """
        ALTER TABLE app.jetons_reinitialisation_mot_de_passe
        DROP CONSTRAINT IF EXISTS chk_reset_type_jeton
        """
    )
    op.execute(
        f"""
        ALTER TABLE app.jetons_reinitialisation_mot_de_passe
        ADD CONSTRAINT chk_reset_type_jeton
        CHECK (type_jeton IN ({values}))
        """
    )


def upgrade() -> None:
    _replace_constraints(_values(RESET_TOKEN_TYPES))


def downgrade() -> None:
    _replace_constraints(_values(PREVIOUS_RESET_TOKEN_TYPES))
