import ast
import json
import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.services.bad_debts_decision import ACTION_BUSINESS_LABELS, compute_client_decision


_FILTER_TIER_FR = {"high": "Élevé", "medium": "Moyen", "low": "Faible"}
_FILTER_SEG_FR = {
    "DISCONNECTED": "Déconnecté",
    "SUSPENDED": "Suspendu",
    "ON-HOLD": "En attente",
    "Bon-payeur": "Bon payeur",
    "Standard": "Standard",
}
_FILTER_ACTION_FR = {
    "call_center_priority": "Appel prioritaire centre de relation client",
    "sms_retention_offer": "SMS personnalisé",
    "monitor_only": "Suivi routine",
}


def _build_filter_summary_fr(active_filters: dict[str, Any]) -> str:
    if not active_filters:
        return "Tous les clients du portefeuille"
    parts: list[str] = []
    if "risk_tier" in active_filters:
        parts.append(f"Risque : {_FILTER_TIER_FR.get(str(active_filters['risk_tier']), str(active_filters['risk_tier']))}")
    if "cluster_name" in active_filters:
        parts.append(f"Segment : {_FILTER_SEG_FR.get(str(active_filters['cluster_name']), str(active_filters['cluster_name']))}")
    if "is_anomaly" in active_filters:
        parts.append(f"Anomalie : {'Oui' if active_filters['is_anomaly'] else 'Non'}")
    if "recommended_action" in active_filters:
        parts.append(f"Action : {_FILTER_ACTION_FR.get(str(active_filters['recommended_action']), str(active_filters['recommended_action']))}")
    if "search" in active_filters:
        parts.append(f"Recherche MSISDN")
    return f"Filtres actifs : {', '.join(parts)}"


CLIENT_COLUMNS = [
    "msisdn",
    "state",
    "cluster_id",
    "cluster_name",
    "risk_level",
    "risk_label",
    "risk_tier",
    "final_risk_score",
    "risk_score_raw",
    "is_anomaly",
    "anomaly_score",
    "top_drivers",
    "avg_credit_amount",
    "avg_reimburse_ratio",
    "avg_days_since_credit",
    "total_outstanding_amount",
    "nb_sos",
    "debt_to_credit",
    "credit_intensity",
    "tenure_days",
    "has_debt",
    "uses_sos",
    "never_repaid",
    "full_repayer",
    "is_dormant_like",
    "imported_at",
]


class BadDebtsService:
    def __init__(self, db: Session):
        self.db = db

    def health(self) -> dict[str, str]:
        return {
            "status": "ok",
            "module": "bad_debts",
            "storage": "postgresql",
            "schema": "ml",
        }

    def get_summary(self) -> dict[str, Any]:
        totals = self.db.execute(
            text(
                """
                SELECT
                    COUNT(*)::int AS total_clients,
                    COUNT(*) FILTER (WHERE LOWER(COALESCE(risk_tier, '')) = 'high')::int AS high_risk_count,
                    COUNT(*) FILTER (WHERE LOWER(COALESCE(risk_tier, '')) = 'medium')::int AS medium_risk_count,
                    COUNT(*) FILTER (WHERE LOWER(COALESCE(risk_tier, '')) = 'low')::int AS low_risk_count,
                    COUNT(*) FILTER (WHERE is_anomaly IS TRUE)::int AS anomaly_count,
                    AVG(final_risk_score) AS avg_final_risk_score,
                    MAX(final_risk_score) AS max_final_risk_score,
                    MAX(imported_at) AS latest_import_at
                FROM ml.bad_debts_clients
                """
            )
        ).mappings().one()

        by_tier = self._count_by("risk_tier")
        by_cluster_name = self._count_by("cluster_name")
        average_debt_by_risk = self._average_debt_by_risk()
        average_score_by_segment = self._average_score_by_segment()
        latest_import = self.get_import_runs(limit=1)

        high = int(totals["high_risk_count"] or 0)
        medium = int(totals["medium_risk_count"] or 0)

        return {
            "date": date.today().isoformat(),
            "total_clients": int(totals["total_clients"] or 0),
            "at_risk_count": high + medium,
            "high_risk_count": high,
            "medium_risk_count": medium,
            "low_risk_count": int(totals["low_risk_count"] or 0),
            "anomaly_count": int(totals["anomaly_count"] or 0),
            "avg_final_risk_score": self._json_value(totals["avg_final_risk_score"]),
            "max_final_risk_score": self._json_value(totals["max_final_risk_score"]),
            "latest_import_at": totals["latest_import_at"],
            "by_tier": {
                "low": int(by_tier.get("low", 0)),
                "medium": int(by_tier.get("medium", 0)),
                "high": int(by_tier.get("high", 0)),
            },
            "by_cluster_name": by_cluster_name,
            "average_debt_by_risk": average_debt_by_risk,
            "average_score_by_segment": average_score_by_segment,
            "latest_import": latest_import[0] if latest_import else None,
        }

    def _average_debt_by_risk(self) -> list[dict[str, Any]]:
        effective_tier_sql = self._effective_tier_case_sql()
        rows = self.db.execute(
            text(
                f"""
                SELECT ({effective_tier_sql}) AS tier, AVG(total_outstanding_amount) AS average_debt
                FROM ml.bad_debts_clients
                GROUP BY ({effective_tier_sql})
                """
            )
        ).mappings().all()
        values = {str(row["tier"] or "").lower(): self._json_value(row["average_debt"]) for row in rows}
        labels = {"low": "Faible", "medium": "Moyen", "high": "Élevé"}
        return [
            {"level": level, "label": labels[level], "value": float(values.get(level) or 0)}
            for level in ("low", "medium", "high")
        ]

    def _average_score_by_segment(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            text(
                """
                SELECT COALESCE(cluster_name, 'unknown') AS segment, AVG(final_risk_score) AS average_score
                FROM ml.bad_debts_clients
                GROUP BY COALESCE(cluster_name, 'unknown')
                ORDER BY AVG(final_risk_score) DESC NULLS LAST, COALESCE(cluster_name, 'unknown') ASC
                """
            )
        ).mappings().all()
        return [
            {
                "segment": str(row["segment"]),
                "label": _FILTER_SEG_FR.get(str(row["segment"]), "Segment non défini" if str(row["segment"]) == "unknown" else str(row["segment"])),
                "value": float(self._json_value(row["average_score"]) or 0),
            }
            for row in rows
        ]

    def list_clients(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        risk_tier: str | None = None,
        cluster_name: str | None = None,
        is_anomaly: bool | None = None,
        recommended_action: str | None = None,
        search: str | None = None,
    ) -> dict[str, Any]:
        page = max(page, 1)
        page_size = min(max(page_size, 1), 200)
        filters, params = self._client_filters(
            risk_tier=risk_tier,
            cluster_name=cluster_name,
            is_anomaly=is_anomaly,
            recommended_action=recommended_action,
            search=search,
        )
        return self._paginated_clients(filters=filters, params=params, page=page, page_size=page_size)

    def list_at_risk_clients(self, *, tier: str = "high", page: int = 1, page_size: int = 50) -> dict[str, Any]:
        page = max(page, 1)
        page_size = min(max(page_size, 1), 500)
        filters, params = self._client_filters(risk_tier=tier or "high")
        return self._paginated_clients(filters=filters, params=params, page=page, page_size=page_size)

    def get_client(self, msisdn: str) -> dict[str, Any] | None:
        row = self.db.execute(
            text(
                f"""
                SELECT {", ".join(CLIENT_COLUMNS)}
                FROM ml.bad_debts_clients
                WHERE msisdn = :msisdn
                """
            ),
            {"msisdn": msisdn},
        ).mappings().first()

        if not row:
            return None

        client = self._normalize_client(row)
        client["actions"] = self._get_agent_actions(msisdn)
        return client

    def get_import_runs(self, *, limit: int = 20) -> list[dict[str, Any]]:
        limit = min(max(int(limit or 20), 1), 100)
        rows = self.db.execute(
            text(
                """
                SELECT id, file_name, rows_imported, status, error_message, imported_at
                FROM ml.ml_import_runs
                ORDER BY imported_at DESC, id DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).mappings().all()
        return [self._json_row(row) for row in rows]

    def _paginated_clients(
        self,
        *,
        filters: list[str],
        params: dict[str, Any],
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
        total = self.db.execute(
            text(f"SELECT COUNT(*)::int FROM ml.bad_debts_clients {where_sql}"),
            params,
        ).scalar_one()
        summary = self._clients_summary(where_sql, params)

        query_params = {**params, "limit": page_size, "offset": (page - 1) * page_size}
        rows = self.db.execute(
            text(
                f"""
                SELECT {", ".join(CLIENT_COLUMNS)}
                FROM ml.bad_debts_clients
                {where_sql}
                ORDER BY final_risk_score DESC NULLS LAST, msisdn ASC
                LIMIT :limit OFFSET :offset
                """
            ),
            query_params,
        ).mappings().all()

        return {
            "items": [self._normalize_client(row) for row in rows],
            "total": int(total or 0),
            "page": page,
            "page_size": page_size,
            "total_pages": math.ceil((total or 0) / page_size) if total else 0,
            "filter_options": self._filter_options(),
            "summary": summary,
        }

    def _clients_summary(self, where_sql: str, params: dict[str, Any]) -> dict[str, Any]:
        effective_tier_sql = self._effective_tier_case_sql()
        recommended_action_sql = self._recommended_action_case_sql()
        row = self.db.execute(
            text(
                f"""
                SELECT
                    COUNT(*)::int AS total_clients,
                    COUNT(*) FILTER (WHERE ({effective_tier_sql}) = 'high')::int AS high_risk_count,
                    AVG(final_risk_score) AS average_score,
                    AVG(avg_reimburse_ratio) AS average_reimburse_ratio,
                    COUNT(*) FILTER (WHERE ({recommended_action_sql}) = 'call_center_priority')::int AS priority_actions_count
                FROM ml.bad_debts_clients
                {where_sql}
                """
            ),
            params,
        ).mappings().one()
        return {
            "total_clients": int(row["total_clients"] or 0),
            "high_risk_count": int(row["high_risk_count"] or 0),
            "average_score": self._json_value(row["average_score"]),
            "average_reimburse_ratio": self._json_value(row["average_reimburse_ratio"]),
            "priority_actions_count": int(row["priority_actions_count"] or 0),
        }

    def _client_filters(
        self,
        *,
        risk_tier: str | None = None,
        cluster_name: str | None = None,
        is_anomaly: bool | None = None,
        recommended_action: str | None = None,
        search: str | None = None,
    ) -> tuple[list[str], dict[str, Any]]:
        filters: list[str] = []
        params: dict[str, Any] = {}

        if risk_tier:
            filters.append(f"({self._effective_tier_case_sql()}) = LOWER(:risk_tier)")
            params["risk_tier"] = risk_tier.strip()
        if cluster_name:
            filters.append("cluster_name = :cluster_name")
            params["cluster_name"] = cluster_name.strip()
        if is_anomaly is not None:
            filters.append("is_anomaly = :is_anomaly")
            params["is_anomaly"] = bool(is_anomaly)
        if recommended_action:
            filters.append(f"{self._recommended_action_case_sql()} = :recommended_action")
            params["recommended_action"] = recommended_action.strip()
        if search:
            filters.append("msisdn ILIKE :search")
            params["search"] = f"%{search.strip()}%"

        return filters, params

    def _filter_options(self) -> dict[str, Any]:
        rows = self.db.execute(
            text(
                f"""
                SELECT {self._recommended_action_case_sql()} AS recommended_action, COUNT(*)::int AS total
                FROM ml.bad_debts_clients
                GROUP BY {self._recommended_action_case_sql()}
                """
            )
        ).mappings().all()
        counts = {str(row["recommended_action"]): int(row["total"] or 0) for row in rows}
        order = ("call_center_priority", "sms_retention_offer", "monitor_only")
        return {
            "recommended_actions": [
                {
                    "value": value,
                    "label": ACTION_BUSINESS_LABELS[value],
                    "count": counts.get(value, 0),
                }
                for value in order
            ]
        }

    @staticmethod
    def _effective_tier_case_sql() -> str:
        return """
            CASE
                WHEN is_anomaly IS TRUE AND LOWER(COALESCE(risk_tier, 'low')) = 'medium' THEN 'high'
                WHEN is_anomaly IS TRUE AND LOWER(COALESCE(risk_tier, 'low')) = 'low' THEN 'medium'
                WHEN LOWER(COALESCE(risk_tier, 'low')) IN ('low', 'medium', 'high') THEN LOWER(COALESCE(risk_tier, 'low'))
                ELSE 'low'
            END
        """

    def _recommended_action_case_sql(self) -> str:
        effective_tier_sql = self._effective_tier_case_sql()
        return f"""
            CASE
                WHEN ({effective_tier_sql}) = 'high' THEN 'call_center_priority'
                WHEN ({effective_tier_sql}) = 'medium' THEN 'sms_retention_offer'
                ELSE 'monitor_only'
            END
        """

    def compute_global_kpis(
        self,
        *,
        risk_tier: str | None = None,
        cluster_name: str | None = None,
        is_anomaly: bool | None = None,
        recommended_action: str | None = None,
        search: str | None = None,
    ) -> dict[str, Any]:
        filters, params = self._client_filters(
            risk_tier=risk_tier,
            cluster_name=cluster_name,
            is_anomaly=is_anomaly,
            recommended_action=recommended_action,
            search=search,
        )
        where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
        effective_tier_sql = self._effective_tier_case_sql()
        recommended_action_sql = self._recommended_action_case_sql()

        row = self.db.execute(
            text(
                f"""
                SELECT
                    COUNT(*)::int AS total_clients,
                    COUNT(*) FILTER (WHERE ({effective_tier_sql}) = 'high')::int AS clients_high,
                    COUNT(*) FILTER (WHERE ({effective_tier_sql}) = 'medium')::int AS clients_medium,
                    COUNT(*) FILTER (WHERE ({effective_tier_sql}) = 'low')::int AS clients_low,
                    COUNT(*) FILTER (WHERE is_anomaly IS TRUE)::int AS clients_with_anomaly,
                    AVG(final_risk_score) AS average_risk_score,
                    AVG(total_outstanding_amount) AS average_debt,
                    AVG(avg_reimburse_ratio) AS average_reimbursement_ratio
                FROM ml.bad_debts_clients {where_sql}
                """
            ),
            params,
        ).mappings().one()

        seg_rows = self.db.execute(
            text(
                f"""
                SELECT COALESCE(cluster_name, 'unknown') AS seg, COUNT(*)::int AS cnt
                FROM ml.bad_debts_clients {where_sql}
                GROUP BY COALESCE(cluster_name, 'unknown') ORDER BY cnt DESC
                """
            ),
            params,
        ).mappings().all()

        risk_rows = self.db.execute(
            text(
                f"""
                SELECT ({effective_tier_sql}) AS tier, COUNT(*)::int AS cnt
                FROM ml.bad_debts_clients {where_sql}
                GROUP BY ({effective_tier_sql}) ORDER BY cnt DESC
                """
            ),
            params,
        ).mappings().all()

        action_rows = self.db.execute(
            text(
                f"""
                SELECT ({recommended_action_sql}) AS action, COUNT(*)::int AS cnt
                FROM ml.bad_debts_clients {where_sql}
                GROUP BY ({recommended_action_sql}) ORDER BY cnt DESC
                """
            ),
            params,
        ).mappings().all()

        dominant_segment = str(seg_rows[0]["seg"]) if seg_rows else None
        dominant_action = str(action_rows[0]["action"]) if action_rows else None

        active_filters = {
            k: v for k, v in {
                "risk_tier": risk_tier,
                "cluster_name": cluster_name,
                "is_anomaly": is_anomaly,
                "recommended_action": recommended_action,
                "search": search,
            }.items() if v is not None
        }
        filter_summary = _build_filter_summary_fr(active_filters)

        return {
            "total_clients": int(row["total_clients"] or 0),
            "clients_high": int(row["clients_high"] or 0),
            "clients_medium": int(row["clients_medium"] or 0),
            "clients_low": int(row["clients_low"] or 0),
            "clients_with_anomaly": int(row["clients_with_anomaly"] or 0),
            "average_risk_score": self._json_value(row["average_risk_score"]),
            "average_debt": self._json_value(row["average_debt"]),
            "average_reimbursement_ratio": self._json_value(row["average_reimbursement_ratio"]),
            "dominant_segment": dominant_segment,
            "dominant_recommended_action": dominant_action,
            "distribution_by_segment": {str(r["seg"]): int(r["cnt"]) for r in seg_rows},
            "distribution_by_risk": {str(r["tier"]): int(r["cnt"]) for r in risk_rows},
            "distribution_by_action": {str(r["action"]): int(r["cnt"]) for r in action_rows},
            "filter_summary": filter_summary,
        }

    def _count_by(self, column_name: str) -> dict[str, int]:
        rows = self.db.execute(
            text(
                f"""
                SELECT COALESCE({column_name}, 'unknown') AS label, COUNT(*)::int AS total
                FROM ml.bad_debts_clients
                GROUP BY COALESCE({column_name}, 'unknown')
                ORDER BY total DESC, label ASC
                """
            )
        ).mappings().all()
        return {str(row["label"]).lower() if column_name == "risk_tier" else str(row["label"]): int(row["total"]) for row in rows}

    def _get_agent_actions(self, msisdn: str) -> list[dict[str, Any]]:
        try:
            columns = self._table_columns("agent_runs")
            if "msisdn" not in columns or "payload" not in columns:
                return []

            rows = self.db.execute(
                text(
                    """
                    SELECT
                        id,
                        COALESCE(finished_at, started_at) AS created_at,
                        payload->'decision' AS decision,
                        payload->'business_analysis' AS business_analysis
                    FROM ml.agent_runs
                    WHERE msisdn = :msisdn
                      AND payload ? 'decision'
                      AND payload ? 'business_analysis'
                    ORDER BY COALESCE(finished_at, started_at) DESC NULLS LAST, id DESC
                    LIMIT 5
                    """
                ),
                {"msisdn": msisdn},
            ).mappings().all()
            actions = []
            for row in rows:
                decision = self._json_value(row["decision"]) or {}
                if not isinstance(decision, dict):
                    decision = {}
                actions.append(
                    {
                        "id": row["id"],
                        "action_type": decision.get("action_type") or decision.get("recommended_action"),
                        "priority": decision.get("priority"),
                        "recommendation": decision.get("recommendation") or decision.get("next_best_action") or decision.get("reason"),
                        "created_at": self._json_value(row["created_at"]),
                        "business_analysis": self._json_value(row["business_analysis"]) or {},
                    }
                )
            return actions
        except SQLAlchemyError:
            self.db.rollback()
            return []

    def _table_columns(self, table_name: str) -> set[str]:
        rows = self.db.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'ml'
                  AND table_name = :table_name
                """
            ),
            {"table_name": table_name},
        ).scalars().all()
        return {str(row) for row in rows}

    def _normalize_client(self, row: Any) -> dict[str, Any]:
        item = self._json_row(row)
        item["top_drivers"] = self._parse_top_drivers(item.get("top_drivers"))
        item.update(compute_client_decision(item))
        return item

    def _parse_top_drivers(self, value: Any) -> Any:
        if value is None or isinstance(value, (list, dict)):
            return value
        raw = str(value).strip()
        if not raw:
            return raw
        for parser in (json.loads, ast.literal_eval):
            try:
                parsed = parser(raw)
                if isinstance(parsed, (list, dict, str, int, float, bool)) or parsed is None:
                    return parsed
            except Exception:
                continue
        return value

    def _json_row(self, row: Any) -> dict[str, Any]:
        return {key: self._json_value(value) for key, value in dict(row).items()}

    def _json_value(self, value: Any) -> Any:
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return value.isoformat()
        return value
