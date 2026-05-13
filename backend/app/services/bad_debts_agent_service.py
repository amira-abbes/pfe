from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.services.bad_debts_service import BadDebtsService, CLIENT_COLUMNS


class AgentRunError(RuntimeError):
    pass


DISCLAIMER = (
    "Explication descriptive basée sur les signaux ML et règles métier, "
    "pas une décision automatique définitive."
)


ACTION_BUSINESS_LABELS = {
    "recovery_review": "Revue recouvrement",
    "sms_reminder": "Rappel SMS",
    "call_center_priority": "Appel prioritaire",
    "monitor_only": "Surveillance simple",
}


def build_client_profile(client: dict[str, Any]) -> dict[str, Any]:
    score = _round_float(client.get("final_risk_score"))
    profile = {
        "msisdn": client.get("msisdn"),
        "state": client.get("state"),
        "cluster_name": client.get("cluster_name"),
        "risk_tier": _normalize_tier(client.get("risk_tier")),
        "risk_label": client.get("risk_label"),
        "final_risk_score": score,
        "is_anomaly": bool(client.get("is_anomaly")),
        "avg_reimburse_ratio": _round_float(client.get("avg_reimburse_ratio")),
        "total_outstanding_amount": _round_float(client.get("total_outstanding_amount")),
        "nb_sos": client.get("nb_sos"),
        "debt_to_credit": _round_float(client.get("debt_to_credit")),
        "tenure_days": _round_float(client.get("tenure_days")),
    }
    profile["summary"] = (
        f"Client {profile['msisdn']} classé {profile['risk_tier']} risk, "
        f"segment {profile.get('cluster_name') or '-'}, score {score}, "
        f"encours {profile.get('total_outstanding_amount')}, "
        f"ratio remboursement {profile.get('avg_reimburse_ratio')}."
    )
    return profile


def build_explanations(client: dict[str, Any]) -> dict[str, Any]:
    primary_factors = _primary_factors(client.get("top_drivers"))
    business_rules: list[str] = []

    if _as_int(client.get("never_repaid")) == 1:
        business_rules.append("Client sans remboursement détecté")
    if _as_float(client.get("avg_reimburse_ratio")) is not None and _as_float(client.get("avg_reimburse_ratio")) < 0.35:
        business_rules.append("Ratio de remboursement faible")
    if _as_float(client.get("total_outstanding_amount")) is not None and _as_float(client.get("total_outstanding_amount")) > 0:
        business_rules.append("Encours restant positif")
    if bool(client.get("is_anomaly")):
        business_rules.append("Comportement atypique détecté")
    if _normalize_tier(client.get("risk_tier")) == "high":
        business_rules.append("Niveau de risque élevé")
    if str(client.get("risk_label") or "").strip().lower() == "blacklist":
        business_rules.append("Client classé Blacklist")
    if _as_int(client.get("full_repayer")) == 1:
        business_rules.append("Historique de remboursement complet détecté")
    if _as_int(client.get("has_debt")) == 1:
        business_rules.append("Client avec dette active")
    if _as_int(client.get("nb_sos")) and _as_int(client.get("nb_sos")) > 0:
        business_rules.append("Usage SOS détecté")

    explanation_bits = []
    if primary_factors:
        labels = [str(item.get("feature") or item.get("name") or item) for item in primary_factors[:3]]
        explanation_bits.append("Facteurs ML principaux : " + ", ".join(labels))
    if business_rules:
        explanation_bits.append("Règles métier déclenchées : " + "; ".join(business_rules))

    return {
        "primary_factors": primary_factors,
        "business_rules": business_rules,
        "explanation_text": ". ".join(explanation_bits) if explanation_bits else "Aucun facteur explicatif dominant détecté.",
        "disclaimer": DISCLAIMER,
    }


def decide_next_action(client: dict[str, Any], explanations: dict[str, Any]) -> dict[str, Any]:
    base_tier = _normalize_tier(client.get("risk_tier"))
    effective_tier = base_tier
    anomaly_escalated = False

    if bool(client.get("is_anomaly")):
        if base_tier == "low":
            effective_tier = "medium"
            anomaly_escalated = True
        elif base_tier == "medium":
            effective_tier = "high"
            anomaly_escalated = True

    action_by_tier = {
        "high": ("call_center_priority", 1, "Contact prioritaire par le centre d'appel"),
        "medium": ("sms_reminder", 2, "Rappel SMS de régularisation"),
        "low": ("monitor_only", 4, "Suivi automatique sans action client agressive"),
    }
    action_type, priority, next_best_action = action_by_tier.get(effective_tier, action_by_tier["low"])

    if anomaly_escalated:
        priority = max(1, priority - 1)

    state = str(client.get("state") or "").strip().upper()
    risk_label = str(client.get("risk_label") or "").strip().lower()
    if state == "DISCONNECTED" or risk_label == "blacklist":
        action_type = "recovery_review"
        priority = 1
        next_best_action = "Vérification recouvrement et traitement prioritaire"

    reason_parts = [f"Tier initial={base_tier}", f"tier effectif={effective_tier}"]
    if anomaly_escalated:
        reason_parts.append("escalade anomalie appliquée")
    if explanations.get("business_rules"):
        reason_parts.append("; ".join(explanations["business_rules"][:3]))

    return {
        "recommended_action": action_type,
        "action_type": action_type,
        "priority": priority,
        "next_best_action": next_best_action,
        "effective_tier": effective_tier,
        "anomaly_escalated": anomaly_escalated,
        "reason": " | ".join(reason_parts),
    }


def generate_message(client: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    state = str(client.get("state") or "").strip().upper()
    risk_label = str(client.get("risk_label") or "").strip().lower()
    if state == "DISCONNECTED" or risk_label == "blacklist":
        return {
            "channel": "internal_review",
            "message_text": "Traitement interne recommandé avant toute communication client.",
            "language": "fr",
            "safe_to_send": False,
        }

    effective_tier = _normalize_tier(decision.get("effective_tier"))
    if effective_tier == "high":
        return {
            "channel": "call",
            "message_text": (
                "Bonjour, votre ligne présente un solde à régulariser. "
                "Merci de consulter votre espace client ou de contacter notre service "
                "afin d’éviter toute restriction supplémentaire."
            ),
            "language": "fr",
            "safe_to_send": True,
        }
    if effective_tier == "medium":
        return {
            "channel": "sms",
            "message_text": (
                "Bonjour, un rappel concernant votre solde est disponible. "
                "Vous pouvez le consulter et le régulariser via votre espace client."
            ),
            "language": "fr",
            "safe_to_send": True,
        }
    return {
        "channel": "monitoring",
        "message_text": "Aucune action client immédiate. Suivi automatique recommandé.",
        "language": "fr",
        "safe_to_send": False,
    }


def log_agent_action(db: Session, msisdn: str, decision: dict[str, Any]) -> dict[str, Any]:
    recommendation = decision.get("next_best_action") or decision.get("reason") or decision.get("recommended_action")
    action_type = decision.get("action_type") or decision.get("recommended_action")
    try:
        existing_action = db.execute(
            text(
                """
                SELECT id, msisdn, action_type, priority, recommendation, status, created_at
                FROM ml.agent_actions
                WHERE msisdn = :msisdn
                  AND action_type = :action_type
                  AND status = 'generated'
                  AND created_at >= NOW() - INTERVAL '10 minutes'
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """
            ),
            {"msisdn": msisdn, "action_type": action_type},
        ).mappings().first()
        if existing_action:
            return {
                "action_logged": False,
                "action_reused": True,
                "stored_action_id": existing_action["id"],
                "reused_action": _json_row(existing_action),
            }

        action_id = db.execute(
            text(
                """
                INSERT INTO ml.agent_actions
                    (msisdn, action_type, priority, recommendation, status)
                VALUES
                    (:msisdn, :action_type, :priority, :recommendation, 'generated')
                RETURNING id
                """
            ),
            {
                "msisdn": msisdn,
                "action_type": action_type,
                "priority": decision.get("priority"),
                "recommendation": recommendation,
            },
        ).scalar_one_or_none()
        db.commit()
        return {"action_logged": True, "action_reused": False, "stored_action_id": action_id}
    except SQLAlchemyError as exc:
        db.rollback()
        return {"action_logged": False, "action_reused": False, "stored_action_id": None, "error": str(exc)}


def log_agent_run(
    db: Session,
    *,
    run_id: str,
    msisdn: str,
    status: str,
    started_at: datetime,
    finished_at: datetime,
    action_id: int | None = None,
    effective_tier: str | None = None,
    anomaly_escalated: bool = False,
    payload: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> int | None:
    try:
        statement = text(
            """
            INSERT INTO ml.agent_runs
                (
                    run_id,
                    msisdn,
                    status,
                    action_id,
                    effective_tier,
                    anomaly_escalated,
                    payload,
                    error_message,
                    started_at,
                    finished_at
                )
            VALUES
                (
                    :run_id,
                    :msisdn,
                    :status,
                    :action_id,
                    :effective_tier,
                    :anomaly_escalated,
                    :payload,
                    :error_message,
                    :started_at,
                    :finished_at
                )
            RETURNING id
            """
        ).bindparams(bindparam("payload", type_=JSONB))
        agent_run_id = db.execute(
            statement,
            {
                "run_id": run_id,
                "msisdn": msisdn,
                "status": status,
                "action_id": action_id,
                "effective_tier": effective_tier,
                "anomaly_escalated": bool(anomaly_escalated),
                "payload": _json_payload(payload or {}),
                "error_message": error_message,
                "started_at": started_at,
                "finished_at": finished_at,
            },
        ).scalar_one_or_none()
        db.commit()
        return agent_run_id
    except Exception:
        db.rollback()
        return None


def log_agent_report(
    db: Session,
    *,
    period_label: str,
    summary: str,
    recommendations: str,
    kpis: dict[str, Any],
) -> int | None:
    try:
        statement = text(
            """
            INSERT INTO ml.agent_reports
                (report_type, period_label, summary, recommendations, kpis_json)
            VALUES
                ('bad_debts_batch', :period_label, :summary, :recommendations, :kpis_json)
            RETURNING id
            """
        ).bindparams(bindparam("kpis_json", type_=JSONB))
        report_id = db.execute(
            statement,
            {
                "period_label": period_label,
                "summary": summary,
                "recommendations": recommendations,
                "kpis_json": _json_payload(kpis),
            },
        ).scalar_one_or_none()
        db.commit()
        return report_id
    except Exception:
        db.rollback()
        return None


def _run_bad_debts_agent_core(db: Session, msisdn: str) -> dict[str, Any] | None:
    client = _load_client(db, msisdn)
    if not client:
        return None

    errors: list[str] = []
    run_id = str(uuid4())
    profile = build_client_profile(client)
    explanations = build_explanations(client)
    decision = decide_next_action(client, explanations)
    message = generate_message(client, decision)
    logging_result = log_agent_action(db, msisdn, decision)

    if not logging_result.get("action_logged") and not logging_result.get("action_reused"):
        errors.append(logging_result.get("error") or "Action non journalisée.")

    decision = {
        **decision,
        "action_logged": bool(logging_result.get("action_logged")),
        "action_reused": bool(logging_result.get("action_reused")),
        "stored_action_id": logging_result.get("stored_action_id"),
        "reused_action": logging_result.get("reused_action"),
    }

    return {
        "run_id": run_id,
        "msisdn": msisdn,
        "profile": profile,
        "explanations": explanations,
        "decision": decision,
        "message": message,
        "errors": errors,
    }


def run_bad_debts_agent(db: Session, msisdn: str) -> dict[str, Any] | None:
    started_at = datetime.utcnow()
    fallback_run_id = str(uuid4())
    try:
        response = _run_bad_debts_agent_core(db, msisdn)
        if not response:
            return None

        run_id = response.get("run_id") or fallback_run_id
        decision = response.get("decision") or {}
        agent_run_id = log_agent_run(
            db,
            run_id=run_id,
            msisdn=msisdn,
            status="success",
            action_id=decision.get("stored_action_id"),
            effective_tier=decision.get("effective_tier"),
            anomaly_escalated=bool(decision.get("anomaly_escalated")),
            payload=response,
            error_message=None,
            started_at=started_at,
            finished_at=datetime.utcnow(),
        )
        if agent_run_id is not None:
            response["agent_run_id"] = agent_run_id
        return response
    except Exception as exc:
        error_message = str(exc) or exc.__class__.__name__
        log_agent_run(
            db,
            run_id=fallback_run_id,
            msisdn=msisdn,
            status="failed",
            action_id=None,
            effective_tier=None,
            anomaly_escalated=False,
            payload={
                "run_id": fallback_run_id,
                "msisdn": msisdn,
                "stage": "run_bad_debts_agent",
                "error_type": exc.__class__.__name__,
            },
            error_message=error_message,
            started_at=started_at,
            finished_at=datetime.utcnow(),
        )
        raise AgentRunError("Impossible d'executer l'agent Bad Debts.") from exc


def run_bad_debts_agent_batch(db: Session, tier: str = "high", limit: int = 50) -> dict[str, Any]:
    normalized_tier = _normalize_tier(tier)
    safe_limit = min(max(int(limit or 50), 1), 200)
    try:
        msisdns = _load_batch_msisdns(db, normalized_tier, safe_limit)
    except Exception:
        db.rollback()
        return {
            "status": "failed",
            "tier": normalized_tier,
            "limit": safe_limit,
            "clients_analyzed": 0,
            "actions_created": 0,
            "actions_reused": 0,
            "errors_count": 1,
            "items": [],
            "message": "Impossible de charger les clients Bad Debts pour le batch.",
        }
    if not msisdns:
        return {
            "status": "empty",
            "tier": normalized_tier,
            "limit": safe_limit,
            "clients_analyzed": 0,
            "actions_created": 0,
            "actions_reused": 0,
            "errors_count": 0,
            "items": [],
            "message": f"Aucun client trouve pour risk_tier={normalized_tier}.",
        }

    items: list[dict[str, Any]] = []
    actions_created = 0
    actions_reused = 0
    errors_count = 0

    for msisdn in msisdns:
        try:
            response = run_bad_debts_agent(db, msisdn)
            if not response:
                errors_count += 1
                items.append(
                    _build_batch_item(
                        msisdn,
                        "failed",
                        error="Client introuvable pendant le batch.",
                    )
                )
                continue

            decision = response.get("decision") or {}
            response_errors = response.get("errors") or []
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
                    action_id=decision.get("stored_action_id"),
                    action_type=decision.get("action_type") or decision.get("recommended_action"),
                    priority=decision.get("priority"),
                    agent_run_id=response.get("agent_run_id"),
                    error=item_error,
                )
            )
        except AgentRunError as exc:
            errors_count += 1
            items.append(
                _build_batch_item(msisdn, "failed", error=str(exc))
            )
        except Exception:
            errors_count += 1
            items.append(
                _build_batch_item(msisdn, "failed", error="Erreur inattendue pendant le batch Bad Debts.")
            )

    if errors_count == 0:
        status_value = "success"
    elif errors_count < len(msisdns):
        status_value = "partial_success"
    else:
        status_value = "failed"

    report_id = None
    report_summary = None
    if status_value in {"success", "partial_success"}:
        generated_at = datetime.utcnow()
        period_label = generated_at.strftime("%d/%m/%Y")
        tier_label = _tier_business_label(normalized_tier)
        error_word = "erreur" if errors_count == 1 else "erreurs"
        report_summary = (
            "Analyse agentic globale terminee : "
            f"{len(msisdns)} clients a risque {tier_label} analyses, "
            f"{actions_created} nouvelles actions generees, "
            f"{actions_reused} actions reutilisees et {errors_count} {error_word}."
        )
        recommendations = (
            "Prioriser les clients classes risque eleve, notamment les profils Blacklist ou DISCONNECTED. "
            "Les actions deja recentes sont reutilisees afin d'eviter les doublons operationnels."
        )
        report_id = log_agent_report(
            db,
            period_label=period_label,
            summary=report_summary,
            recommendations=recommendations,
            kpis={
                "tier": normalized_tier,
                "limit": safe_limit,
                "clients_analyzed": len(msisdns),
                "actions_created": actions_created,
                "actions_reused": actions_reused,
                "errors_count": errors_count,
                "status": status_value,
                "generated_at": generated_at.isoformat(),
            },
        )

    return {
        "status": status_value,
        "tier": normalized_tier,
        "limit": safe_limit,
        "clients_analyzed": len(msisdns),
        "actions_created": actions_created,
        "actions_reused": actions_reused,
        "errors_count": errors_count,
        "items": items,
        "report_id": report_id,
        "report_summary": report_summary,
    }


def get_recent_agent_actions(db: Session, limit: int = 20) -> list[dict[str, Any]]:
    limit = min(max(int(limit or 20), 1), 100)
    rows = db.execute(
        text(
            """
            SELECT id, msisdn, action_type, priority, recommendation, status, created_at
            FROM ml.agent_actions
            ORDER BY created_at DESC, id DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).mappings().all()
    return [_json_row(row) for row in rows]


def get_recent_agent_reports(db: Session, limit: int = 10) -> list[dict[str, Any]]:
    limit = min(max(int(limit or 10), 1), 50)
    rows = db.execute(
        text(
            """
            SELECT id, report_type, period_label, summary, recommendations, kpis_json, generated_at
            FROM ml.agent_reports
            WHERE report_type = 'bad_debts_batch'
            ORDER BY generated_at DESC, id DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).mappings().all()
    return [_json_row(row) for row in rows]


def _build_batch_item(
    msisdn: str,
    status: str,
    *,
    action_id: int | None = None,
    action_type: str | None = None,
    priority: int | None = None,
    agent_run_id: int | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    action_label = ACTION_BUSINESS_LABELS.get(str(action_type or ""), action_type)
    priority_label = _priority_label(priority)
    return {
        "msisdn": msisdn,
        "client_label": f"Client {msisdn}" if msisdn else "Client",
        "status": status,
        "processing_label": _processing_label(status),
        "action_id": action_id,
        "action_type": action_type,
        "action_label": action_label,
        "priority": priority,
        "priority_label": priority_label,
        "agent_run_id": agent_run_id,
        "business_comment": _business_comment(status, action_type, priority, error),
        "error": error,
    }


def _processing_label(status: str) -> str:
    if status == "success":
        return "Nouvelle action generee"
    if status == "reused":
        return "Deja traite recemment"
    if status == "failed":
        return "Erreur de traitement"
    return status or "-"


def _priority_label(priority: Any) -> str:
    try:
        numeric = int(priority)
    except (TypeError, ValueError):
        return "Priorite standard"
    if numeric in {1, 2, 3}:
        return f"Priorite {numeric}"
    return "Priorite standard"


def _business_comment(status: str, action_type: str | None, priority: Any, error: str | None) -> str:
    if status == "reused":
        return "Action recente reutilisee pour eviter un doublon."
    if status == "failed":
        return error or "Le traitement agentic n'a pas abouti pour ce client."
    action_label = ACTION_BUSINESS_LABELS.get(str(action_type or ""), "action de suivi")
    if _priority_label(priority) == "Priorite 1":
        return f"Client a risque eleve necessitant une {action_label.lower()}."
    return f"Client oriente vers {action_label.lower()} selon le scoring Bad Debts."


def _tier_business_label(tier: str) -> str:
    if tier == "high":
        return "eleve"
    if tier == "medium":
        return "moyen"
    return "faible"


def _load_client(db: Session, msisdn: str) -> dict[str, Any] | None:
    row = db.execute(
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
    return BadDebtsService(db)._normalize_client(row)


def _load_batch_msisdns(db: Session, tier: str, limit: int) -> list[str]:
    rows = db.execute(
        text(
            """
            SELECT msisdn
            FROM ml.bad_debts_clients
            WHERE LOWER(COALESCE(risk_tier, '')) = :tier
            ORDER BY final_risk_score DESC NULLS LAST, msisdn ASC
            LIMIT :limit
            """
        ),
        {"tier": tier, "limit": limit},
    ).mappings().all()
    return [str(row["msisdn"]) for row in rows if row.get("msisdn") is not None]


def _primary_factors(top_drivers: Any) -> list[Any]:
    if isinstance(top_drivers, list):
        return top_drivers
    if isinstance(top_drivers, dict):
        return [top_drivers]
    if top_drivers:
        return [top_drivers]
    return []


def _normalize_tier(value: Any) -> str:
    tier = str(value or "low").strip().lower()
    return tier if tier in {"low", "medium", "high"} else "low"


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _round_float(value: Any, digits: int = 3) -> float | None:
    numeric = _as_float(value)
    return round(numeric, digits) if numeric is not None else None


def _json_row(row: Any) -> dict[str, Any]:
    return {key: _json_value(value) for key, value in dict(row).items()}


def _json_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_payload(item) for item in value]
    if isinstance(value, tuple):
        return [_json_payload(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value
    return value
