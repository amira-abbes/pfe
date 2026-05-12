from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.services.bad_debts_service import BadDebtsService, CLIENT_COLUMNS


DISCLAIMER = (
    "Explication descriptive basée sur les signaux ML et règles métier, "
    "pas une décision automatique définitive."
)


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


def run_bad_debts_agent(db: Session, msisdn: str) -> dict[str, Any] | None:
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


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value
    return value
