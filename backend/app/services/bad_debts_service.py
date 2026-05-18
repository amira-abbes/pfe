import ast
import json
import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


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
            "latest_import": latest_import[0] if latest_import else None,
        }

    def list_clients(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        risk_tier: str | None = None,
        cluster_name: str | None = None,
        is_anomaly: bool | None = None,
        search: str | None = None,
    ) -> dict[str, Any]:
        page = max(page, 1)
        page_size = min(max(page_size, 1), 200)
        filters, params = self._client_filters(
            risk_tier=risk_tier,
            cluster_name=cluster_name,
            is_anomaly=is_anomaly,
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

    def get_n8n_summary(self) -> dict[str, Any]:
        summary = self.get_summary()
        return {
            "date": summary["date"],
            "at_risk_count": summary["at_risk_count"],
            "messages_sent": self._messages_sent_count(),
            "anomaly_count": summary["anomaly_count"],
            "total_clients_scored": summary["total_clients"],
            "by_tier": summary["by_tier"],
            "by_cluster_name": summary["by_cluster_name"],
        }

    def get_n8n_at_risk_clients(self, *, tier: str = "high", page: int = 1, page_size: int = 50) -> dict[str, Any]:
        page_data = self.list_at_risk_clients(tier=tier, page=page, page_size=page_size)
        return {
            "items": [
                {
                    "msisdn": item["msisdn"],
                    "risk_tier": item.get("risk_tier"),
                    "final_risk_score": item.get("final_risk_score"),
                    "risk_label": item.get("risk_label"),
                    "cluster_name": item.get("cluster_name"),
                    "is_anomaly": item.get("is_anomaly"),
                }
                for item in page_data["items"]
            ],
            "total": page_data["total"],
            "page": page_data["page"],
            "page_size": page_data["page_size"],
        }

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
        }

    def _client_filters(
        self,
        *,
        risk_tier: str | None = None,
        cluster_name: str | None = None,
        is_anomaly: bool | None = None,
        search: str | None = None,
    ) -> tuple[list[str], dict[str, Any]]:
        filters: list[str] = []
        params: dict[str, Any] = {}

        if risk_tier:
            filters.append("LOWER(COALESCE(risk_tier, '')) = LOWER(:risk_tier)")
            params["risk_tier"] = risk_tier.strip()
        if cluster_name:
            filters.append("cluster_name = :cluster_name")
            params["cluster_name"] = cluster_name.strip()
        if is_anomaly is not None:
            filters.append("is_anomaly = :is_anomaly")
            params["is_anomaly"] = bool(is_anomaly)
        if search:
            filters.append("msisdn ILIKE :search")
            params["search"] = f"%{search.strip()}%"

        return filters, params

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
            columns = self._table_columns("agent_actions")
            if "msisdn" not in columns:
                return []

            order_column = next((col for col in ("created_at", "imported_at", "executed_at", "action_at") if col in columns), None)
            order_sql = f"ORDER BY a.{order_column} DESC" if order_column else ""
            rows = self.db.execute(
                text(
                    f"""
                    SELECT to_jsonb(a) AS action
                    FROM ml.agent_actions AS a
                    WHERE a.msisdn = :msisdn
                    {order_sql}
                    LIMIT 50
                    """
                ),
                {"msisdn": msisdn},
            ).mappings().all()
            return [self._json_value(row["action"]) for row in rows]
        except SQLAlchemyError:
            self.db.rollback()
            return []

    def _messages_sent_count(self) -> int:
        try:
            columns = self._table_columns("agent_actions")
            if not columns:
                return 0

            predicates = []
            for column in ("action_type", "action_name", "type"):
                if column in columns:
                    predicates.append(f"LOWER(COALESCE({column}, '')) LIKE '%message%'")
            if "status" in columns:
                predicates.append("LOWER(COALESCE(status, '')) IN ('sent', 'success', 'completed')")
            if not predicates:
                return 0

            return int(
                self.db.execute(
                    text(
                        f"""
                        SELECT COUNT(*)::int
                        FROM ml.agent_actions
                        WHERE {" OR ".join(predicates)}
                        """
                    )
                ).scalar()
                or 0
            )
        except SQLAlchemyError:
            self.db.rollback()
            return 0

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
