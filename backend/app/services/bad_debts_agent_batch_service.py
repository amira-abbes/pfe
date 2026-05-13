from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.agents.graph import run_agent_graph
from app.agents.nodes import safe_llm_generate_batch_summary
from app.services.bad_debts_agent_service import _build_batch_item, log_agent_report
from app.services.bad_debts_service import BadDebtsService


def run_bad_debts_langgraph_batch(db: Session, tier: str = "high", limit: int = 50) -> dict[str, Any]:
    normalized_tier = _normalize_batch_tier(tier)
    safe_limit = min(max(int(limit or 50), 1), 200)
    page = BadDebtsService(db).list_at_risk_clients(
        tier=normalized_tier,
        page=1,
        page_size=safe_limit,
    )
    clients = page.get("items") or []

    if not clients:
        return {
            "status": "empty",
            "tier": normalized_tier,
            "limit": safe_limit,
            "clients_analyzed": 0,
            "actions_created": 0,
            "actions_reused": 0,
            "errors_count": 0,
            "items": [],
            "report_id": None,
            "report_summary": None,
            "message": f"Aucun client trouve pour risk_tier={normalized_tier}.",
        }

    items: list[dict[str, Any]] = []
    actions_created = 0
    actions_reused = 0
    errors_count = 0

    for client in clients:
        msisdn = str(client.get("msisdn") or "")
        try:
            graph_result = run_agent_graph(msisdn, db=db, client=client, enable_llm=False)
            decision = graph_result.get("decision") or {}
            response_errors = graph_result.get("errors") or []
            action_logged = bool(decision.get("action_logged"))
            action_reused = bool(decision.get("action_reused"))

            if action_logged:
                actions_created += 1
            if action_reused:
                actions_reused += 1

            item_status = "reused" if action_reused else "success"
            item_error = None
            if response_errors:
                errors_count += 1
                item_status = "failed"
                item_error = "; ".join(str(error) for error in response_errors)

            items.append(
                _build_batch_item(
                    msisdn,
                    item_status,
                    action_id=graph_result.get("action_id") or decision.get("stored_action_id"),
                    action_type=decision.get("action_type") or decision.get("recommended_action"),
                    priority=decision.get("priority"),
                    agent_run_id=graph_result.get("agent_run_id"),
                    error=item_error,
                )
            )
        except Exception as exc:
            errors_count += 1
            items.append(
                _build_batch_item(
                    msisdn,
                    "failed",
                    error=str(exc) or "Erreur inattendue pendant le batch Bad Debts LangGraph.",
                )
            )

    status_value = _batch_status(errors_count, len(clients))
    report_id = None
    report_summary = None

    if status_value in {"success", "partial_success"}:
        report_id, report_summary = _log_langgraph_batch_report(
            db,
            normalized_tier=normalized_tier,
            safe_limit=safe_limit,
            clients_count=len(clients),
            actions_created=actions_created,
            actions_reused=actions_reused,
            errors_count=errors_count,
            status_value=status_value,
            items=items,
        )

    return {
        "status": status_value,
        "tier": normalized_tier,
        "limit": safe_limit,
        "clients_analyzed": len(clients),
        "actions_created": actions_created,
        "actions_reused": actions_reused,
        "errors_count": errors_count,
        "items": items,
        "report_id": report_id,
        "report_summary": report_summary,
        "message": None,
    }


def _log_langgraph_batch_report(
    db: Session,
    *,
    normalized_tier: str,
    safe_limit: int,
    clients_count: int,
    actions_created: int,
    actions_reused: int,
    errors_count: int,
    status_value: str,
    items: list[dict[str, Any]],
) -> tuple[int | None, str]:
    generated_at = datetime.utcnow()
    tier_label = _batch_tier_business_label(normalized_tier)
    error_word = "erreur" if errors_count == 1 else "erreurs"
    report_summary = (
        "Analyse agentic LangGraph terminee : "
        f"{clients_count} clients a risque {tier_label} analyses, "
        f"{actions_created} nouvelles actions generees, "
        f"{actions_reused} actions reutilisees et {errors_count} {error_word}."
    )
    recommendations = (
        "Prioriser les clients classes risque eleve, notamment les profils Blacklist ou DISCONNECTED. "
        "Les actions deja recentes sont reutilisees afin d'eviter les doublons operationnels."
    )
    action_counts = _count_action_types(items)
    ai_summary = safe_llm_generate_batch_summary(
        {
            "tier": normalized_tier,
            "limit": safe_limit,
            "clients_analyzed": clients_count,
            "actions_created": actions_created,
            "actions_reused": actions_reused,
            "errors_count": errors_count,
            "top_action_types": action_counts,
            "examples": _masked_batch_examples(items),
            "decision_locked": True,
        }
    )
    if ai_summary.get("summary") and ai_summary.get("recommendations"):
        report_summary = str(ai_summary["summary"])
        recommendations = str(ai_summary["recommendations"])

    report_id = log_agent_report(
        db,
        period_label=f"{tier_label} - {generated_at.strftime('%d/%m/%Y')}",
        summary=report_summary,
        recommendations=recommendations,
        kpis={
            "tier": normalized_tier,
            "limit": safe_limit,
            "clients_analyzed": clients_count,
            "actions_created": actions_created,
            "actions_reused": actions_reused,
            "errors_count": errors_count,
            "status": status_value,
            "generated_at": generated_at.isoformat(),
            "orchestrator": "langgraph",
            "ai_summary_used": bool(ai_summary.get("ai_summary_used")),
            "llm_model": ai_summary.get("llm_model"),
            "llm_error": ai_summary.get("llm_error"),
            "ai_summary_duration_ms": ai_summary.get("ai_summary_duration_ms"),
            "batch_llm_strategy": "single_global_summary",
            "client_llm_calls": 0,
            "decision_locked": True,
            "top_action_types": action_counts,
        },
    )
    return report_id, report_summary


def _batch_status(errors_count: int, clients_count: int) -> str:
    if errors_count == 0:
        return "success"
    if errors_count < clients_count:
        return "partial_success"
    return "failed"


def _normalize_batch_tier(value: Any) -> str:
    tier = str(value or "high").strip().lower()
    return tier if tier in {"low", "medium", "high"} else "high"


def _batch_tier_business_label(tier: str) -> str:
    if tier == "high":
        return "eleve"
    if tier == "medium":
        return "moyen"
    return "faible"


def _count_action_types(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        action_type = str(item.get("action_type") or "unknown")
        counts[action_type] = counts.get(action_type, 0) + 1
    return counts


def _masked_batch_examples(items: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    examples = []
    for item in items[:limit]:
        examples.append(
            {
                "msisdn": _mask_msisdn(item.get("msisdn")),
                "status": item.get("status"),
                "action_type": item.get("action_type"),
                "priority": item.get("priority"),
                "error": item.get("error"),
            }
        )
    return examples


def _mask_msisdn(value: Any) -> str:
    text = str(value or "")
    if len(text) <= 4:
        return "****"
    return f"{text[:3]}****{text[-2:]}"
