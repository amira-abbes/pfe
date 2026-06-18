"""enforce one active admin per department

Revision ID: 20260616_002
Revises: 20260616_001
Create Date: 2026-06-16
"""

from alembic import op
import sqlalchemy as sa

revision = "20260616_002"
down_revision = "20260616_001"
branch_labels = None
depends_on = None


CONFLICT_REPORT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS app.admin_department_admin_conflicts (
    id BIGSERIAL PRIMARY KEY,
    generated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    departement_id UUID,
    nom_departement VARCHAR(100),
    active_admin_count INTEGER NOT NULL,
    admin_emails TEXT NOT NULL,
    admin_ids TEXT NOT NULL
)
"""


CONFLICT_QUERY_SQL = """
SELECT
    u.departement_id,
    COALESCE(d.nom_departement, 'Departement non renseigne') AS nom_departement,
    COUNT(*)::int AS active_admin_count,
    STRING_AGG(u.email, ', ' ORDER BY u.email) AS admin_emails,
    STRING_AGG(u.id::text, ', ' ORDER BY u.email) AS admin_ids
FROM app.utilisateurs u
LEFT JOIN app.departements d ON d.id = u.departement_id
WHERE UPPER(u.role) = 'ADMIN'
  AND u.est_actif IS TRUE
  AND u.date_suppression IS NULL
GROUP BY u.departement_id, d.nom_departement
HAVING COUNT(*) > 1
ORDER BY COALESCE(d.nom_departement, 'Departement non renseigne')
"""


def _detect_conflicts() -> list[dict]:
    bind = op.get_bind()
    return [dict(row) for row in bind.execute(sa.text(CONFLICT_QUERY_SQL)).mappings().all()]


def _write_conflict_report(conflicts: list[dict]) -> None:
    with op.get_context().autocommit_block():
        op.execute(CONFLICT_REPORT_TABLE_SQL)
        for conflict in conflicts:
            op.execute(
                sa.text(
                    """
                    INSERT INTO app.admin_department_admin_conflicts (
                        departement_id,
                        nom_departement,
                        active_admin_count,
                        admin_emails,
                        admin_ids
                    )
                    VALUES (
                        :departement_id,
                        :nom_departement,
                        :active_admin_count,
                        :admin_emails,
                        :admin_ids
                    )
                    """
                ).bindparams(**conflict)
            )


def upgrade() -> None:
    conflicts = _detect_conflicts()
    if conflicts:
        _write_conflict_report(conflicts)
        lines = [
            "Des departements possedent deja plusieurs administrateurs actifs.",
            "Aucun compte n'a ete modifie. Resolvez les doublons puis relancez la migration.",
            "Rapport en base: app.admin_department_admin_conflicts",
        ]
        for conflict in conflicts:
            lines.append(
                "- {nom_departement}: {active_admin_count} admins actifs ({admin_emails})".format(
                    **conflict
                )
            )
        raise RuntimeError("\n".join(lines))

    op.create_index(
        "ux_utilisateurs_active_admin_per_departement",
        "utilisateurs",
        ["departement_id"],
        unique=True,
        schema="app",
        postgresql_where=sa.text(
            "role = 'ADMIN' AND est_actif IS TRUE AND date_suppression IS NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "ux_utilisateurs_active_admin_per_departement",
        table_name="utilisateurs",
        schema="app",
    )
