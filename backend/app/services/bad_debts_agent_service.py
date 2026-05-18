from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.services.bad_debts_decision import (
    ACTION_BUSINESS_LABELS,
    DECISION_POLICY_VERSION,
    PRIORITY_BUSINESS_LABELS,
    compute_client_decision,
    effective_risk_tier,
)
from app.services.bad_debts_service import BadDebtsService, CLIENT_COLUMNS


class AgentRunError(RuntimeError):
    pass


DISCLAIMER = (
    "Explication descriptive basée sur les signaux ML et règles métier, "
    "pas une décision automatique définitive."
)


ML_SIGNATURE_FIELDS = (
    "msisdn",
    "risk_tier",
    "final_risk_score",
    "cluster_name",
    "state",
    "risk_label",
    "is_anomaly",
    "total_outstanding_amount",
    "top_drivers",
    "anomaly_score",
    "avg_credit_amount",
    "avg_reimburse_ratio",
    "debt_to_credit",
    "nb_sos",
    "has_debt",
    "uses_sos",
    "credit_intensity",
    "tenure_days",
    "never_repaid",
    "full_repayer",
    "is_dormant_like",
)

def build_client_profile(client: dict[str, Any]) -> dict[str, Any]:
    score = _round_float(client.get("final_risk_score"))
    risk_tier = _normalize_tier(client.get("risk_tier"))
    profile = {
        "msisdn": client.get("msisdn"),
        "state": client.get("state"),
        "cluster_name": client.get("cluster_name"),
        "risk_tier": risk_tier,
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
        f"Client {profile['msisdn']} classé en risque {_tier_business_label(risk_tier)}, "
        f"segment {_segment_business_label(profile.get('cluster_name'))}, score {score}, "
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
        business_rules.append("Client à vérifier en priorité")
    if _as_int(client.get("full_repayer")) == 1:
        business_rules.append("Remboursement intégral observé")
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
    decision = compute_client_decision(client)
    reason_parts = [f"Tier initial={decision['raw_risk_tier']}", f"tier effectif={decision['effective_tier']}"]
    if decision["anomaly_escalated"]:
        reason_parts.append("escalade anomalie appliquée")
    if explanations.get("business_rules"):
        reason_parts.append("; ".join(explanations["business_rules"][:3]))
    return {
        **decision,
        "action_type": decision["recommended_action"],
        "reason": " | ".join(reason_parts),
    }


def generate_message(client: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    effective_tier = _normalize_tier(decision.get("effective_tier"))
    if effective_tier == "high":
        content = (
            "Contacter le client via le centre de relation client afin de qualifier la situation, "
            "vérifier les informations disponibles et orienter le suivi selon les règles métier internes."
        )
        return {
            "contact_type": "call_script",
            "title": "Script conseiller",
            "channel": "call",
            "message_text": content,
            "content": content,
            "language": "fr",
            "internal_notice": "Proposition interne non envoyée automatiquement.",
            "safe_to_send": False,
            "generated_by": "deterministic_template",
            "llm_used": False,
        }
    if effective_tier == "medium":
        debt = _as_float(client.get("total_outstanding_amount"))
        if debt and debt > 0:
            debt_text = _format_amount(debt)
            content = (
                f"Bonjour, votre ligne présente un solde à suivre de {debt_text} TND. "
                "Merci de vérifier votre situation ou de contacter le service client pour plus d’informations."
            )
        else:
            content = (
                "Bonjour, un suivi de votre ligne est recommandé. "
                "Merci de vérifier votre situation ou de contacter le service client pour plus d’informations."
            )
        return {
            "contact_type": "preventive_sms",
            "title": "SMS personnalisé proposé",
            "channel": "sms",
            "message_text": content,
            "content": content,
            "language": "fr",
            "internal_notice": "Proposition interne à valider avant envoi.",
            "safe_to_send": True,
            "generated_by": "deterministic_template",
            "llm_used": False,
        }
    content = "Aucune action immédiate n’est recommandée. Conserver un suivi périodique lors des prochains imports."
    return {
        "contact_type": "monitoring_note",
        "title": "Note de suivi",
        "channel": "monitoring",
        "message_text": content,
        "content": content,
        "language": "fr",
        "internal_notice": "Proposition interne non envoyée automatiquement.",
        "safe_to_send": False,
        "generated_by": "deterministic_template",
        "llm_used": False,
    }


def _build_kpi_factors(client: dict[str, Any], profile: dict[str, Any], decision: dict[str, Any], explanations: dict[str, Any]) -> list[str]:
    factors = []
    
    effective_tier_value = _normalize_tier(decision.get("effective_tier") or profile.get("risk_tier") or client.get("risk_tier"))
    factors.append(f"Niveau de risque effectif {_tier_business_label(effective_tier_value)}")
    
    score = _as_float(profile.get("final_risk_score") if profile else client.get("final_risk_score"))
    if score is not None:
        factors.append(f"Score de risque ML : {_format_optional(score)}")
        
    if bool(client.get("is_anomaly") or decision.get("anomaly_escalated")):
        factors.append("Anomalie détectée")
        
    debt = _as_float(client.get("total_outstanding_amount"))
    debt_str = _format_amount(debt).replace(".", ",") if debt is not None else "0"
    
    reimburse_ratio = _as_float(client.get("avg_reimburse_ratio"))
    rate_pct = int(round(reimburse_ratio * 100)) if reimburse_ratio is not None else None
    
    avg_credit = _as_float(client.get("avg_credit_amount"))
    avg_credit_str = _format_amount(avg_credit).replace(".", ",") if avg_credit is not None else None
    
    nb_sos = _as_int(client.get("nb_sos"))
    
    debt_to_credit = _as_float(client.get("debt_to_credit"))

    raw_drivers = explanations.get("primary_factors") or client.get("top_drivers") or []
    driver_keys = [str(item.get("feature") or item.get("name") or item).lower() if isinstance(item, dict) else str(item or "").lower() for item in raw_drivers]
    bus_rules_lower = [r.lower() for r in (explanations.get("business_rules") or [])]

    if debt is not None and debt > 0:
        is_high_debt = (debt_to_credit is not None and debt_to_credit > 0.5) or any(k in ["debt_to_credit"] for k in driver_keys) or any("dette" in r for r in bus_rules_lower)
        if is_high_debt:
            factors.append(f"Encours restant significatif : {debt_str} TND")
        else:
            factors.append(f"Encours restant : {debt_str} TND")
    elif debt is not None and debt == 0:
        factors.append("Pas d’encours restant identifié")

    if rate_pct is None or rate_pct == 0:
        factors.append("Aucun remboursement détecté")
    elif rate_pct >= 95:
        factors.append(f"Remboursement complet observé : {rate_pct} %")
    elif rate_pct >= 60:
        factors.append(f"Remboursement partiel mais acceptable : {rate_pct} %")
    elif rate_pct >= 30:
        factors.append(f"Remboursement partiel observé : {rate_pct} %")
    else:
        factors.append(f"Remboursement faible observé : {rate_pct} %")

    if any(k in ["avg_credit_amount"] for k in driver_keys) or any("montant moyen" in r for r in bus_rules_lower):
        if avg_credit_str:
            factors.append(f"Montant moyen crédité : {avg_credit_str} TND")
        else:
            factors.append("Montant moyen crédité")

    if any(k in ["credit_intensity", "nb_sos"] for k in driver_keys) or any("sos" in r for r in bus_rules_lower):
        if nb_sos is not None:
            factors.append(f"Fréquence d’utilisation SOS : {nb_sos} opérations")
        else:
            factors.append("Fréquence d’utilisation SOS")

    return _unique_non_empty(factors)


def build_deterministic_client_analysis(
    client: dict[str, Any],
    profile: dict[str, Any],
    explanations: dict[str, Any],
    decision: dict[str, Any],
) -> dict[str, Any]:
    effective_tier_value = _normalize_tier(decision.get("effective_tier") or profile.get("risk_tier") or client.get("risk_tier"))
    action_type = str(decision.get("action_type") or decision.get("recommended_action") or "monitor_only")
    action_label = _action_business_label(action_type)
    priority_label = _priority_label(decision.get("priority"))
    score = _as_float(profile.get("final_risk_score") if profile else client.get("final_risk_score"))

    if effective_tier_value == "high":
        decision_reasoning = (
            "Les signaux ML indiquent un niveau de risque élevé. "
            "L’action recommandée est un appel prioritaire par le centre de relation client afin de vérifier "
            "la situation avant toute décision métier."
        )
        next_steps = [
            "Vérifier le profil client dans le contexte métier.",
            "Prioriser le traitement par l’équipe concernée.",
            "Utiliser cette recommandation comme aide à la décision.",
        ]
        confidence_level = "élevée" if score is not None and score >= 0.5 else "moyenne"
    elif effective_tier_value == "medium":
        decision_reasoning = (
            "Les signaux ML indiquent un niveau de risque moyen. "
            "L’action recommandée est un SMS personnalisé afin d’assurer un suivi adapté sans créer d’urgence artificielle."
        )
        next_steps = [
            "Vérifier les signaux de remboursement disponibles.",
            "Préparer un suivi client personnalisé si le contexte métier le confirme.",
            "Utiliser cette recommandation comme aide à la décision.",
        ]
        confidence_level = "moyenne"
    else:
        decision_reasoning = (
            "Les signaux ML indiquent un niveau de risque faible. "
            "L’action recommandée est un suivi routine, sans action immédiate prioritaire."
        )
        next_steps = [
            "Maintenir le suivi routine du client.",
            "Réexaminer le profil si de nouveaux signaux ML apparaissent.",
            "Utiliser cette recommandation comme aide à la décision.",
        ]
        confidence_level = "moyenne"

    key_risk_factors = _build_kpi_factors(client, profile, decision, explanations)

    return {
        "business_summary": (
            f"Client classé en risque {_tier_business_label(effective_tier_value)}, "
            f"segment {_segment_business_label(client.get('cluster_name') or client.get('state'))}, "
            f"avec l’action recommandée « {action_label} » et une priorité « {priority_label} »."
        ),
        "decision_reasoning": decision_reasoning,
        "key_risk_factors": _unique_non_empty(key_risk_factors),
        "recommended_next_steps": next_steps,
        "internal_note": (
            "Cette analyse est générée à partir des signaux ML disponibles et ne constitue pas une décision automatique."
        ),
        "confidence_level": confidence_level,
        "analysis_source": "deterministic_nodes",
    }


def build_client_ml_signature(client: dict[str, Any]) -> dict[str, Any]:
    fields = {field: _normalize_signature_value(client.get(field)) for field in ML_SIGNATURE_FIELDS}
    encoded = json.dumps(fields, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return {
        "ml_signature": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        "ml_signature_fields": fields,
    }


def get_reusable_agent_run_response(
    db: Session,
    msisdn: str,
    ml_signature: str,
) -> dict[str, Any] | None:
    try:
        row = db.execute(
            text(
                """
                SELECT id, run_id, msisdn, action_id, payload, started_at, finished_at
                FROM ml.agent_runs
                WHERE msisdn = :msisdn
                ORDER BY started_at DESC NULLS LAST, id DESC
                LIMIT 1
                """
            ),
            {"msisdn": msisdn},
        ).mappings().first()
    except SQLAlchemyError:
        db.rollback()
        return None

    if not row:
        return None

    payload = _json_value(row["payload"])
    if not isinstance(payload, dict):
        return None
    if payload.get("ml_signature") != ml_signature:
        return None
    if payload.get("decision_policy_version") != DECISION_POLICY_VERSION:
        return None
    if not _is_complete_agent_payload(payload):
        return None

    decision = dict(payload.get("decision") or {})
    action_id = row.get("action_id") or payload.get("action_id") or decision.get("stored_action_id")
    if action_id is not None:
        decision.setdefault("stored_action_id", action_id)
    client = _load_client(db, msisdn) or (payload.get("profile") or {})
    if (
        str(decision.get("action_type") or decision.get("recommended_action") or "") == "sms_retention_offer"
        and bool(client.get("is_anomaly"))
    ):
        return None
    message = payload.get("message") or {}
    if _should_refresh_reused_message(message, decision):
        message = generate_message(client, decision)
    try:
        refreshed_analysis = build_deterministic_client_analysis(
            client,
            build_client_profile(client),
            build_explanations(client),
            decision,
        )
    except Exception:
        refreshed_analysis = payload.get("ai_analysis") or {}

    return {
        "run_id": row.get("run_id") or payload.get("run_id"),
        "msisdn": row.get("msisdn") or payload.get("msisdn") or msisdn,
        "profile": payload.get("profile") or {},
        "explanations": payload.get("explanations") or {},
        "decision": decision,
        "message": message,
        "ai_analysis": refreshed_analysis,
        "action_id": action_id,
        "agent_run_id": row.get("id"),
        "errors": [],
        "reused_existing_analysis": True,
    }


def _should_refresh_reused_message(message: dict[str, Any], decision: dict[str, Any]) -> bool:
    action = str(decision.get("action_type") or decision.get("recommended_action") or "")
    text = str((message or {}).get("message_text") or (message or {}).get("content") or "").lower()
    if action in {"call_center_priority", "monitor_only"}:
        return True
    if action == "sms_retention_offer" and bool(decision.get("anomaly_escalated")) and (message or {}).get("contact_type") != "preventive_sms_ai":
        return True
    forbidden_reused_terms = (
        "plan d'apurement",
        "plan d’apurement",
        "offre de restructuration",
        "remise",
        "réduction",
        "bonus",
        "sanction",
        "menace",
        "contentieux",
        "poursuite",
        "recouvrement agressif",
        "bonjour, je suis un conseiller",
    )
    return any(term in text for term in forbidden_reused_terms)


def log_agent_action(db: Session, msisdn: str, decision: dict[str, Any]) -> dict[str, Any]:
    recommendation = decision.get("next_best_action") or decision.get("reason") or decision.get("recommended_action")
    action_type = decision.get("action_type") or decision.get("recommended_action")
    try:
        existing_action = db.execute(
            text(
                """
                SELECT id, msisdn, action_type, priority, recommendation, created_at
                FROM ml.agent_actions
                WHERE msisdn = :msisdn
                  AND action_type = :action_type
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


def _run_bad_debts_agent_core(db: Session, msisdn: str) -> dict[str, Any] | None:
    client = _load_client(db, msisdn)
    if not client:
        return None

    errors: list[str] = []
    run_id = str(uuid4())
    signature_data = build_client_ml_signature(client)
    profile = build_client_profile(client)
    explanations = build_explanations(client)
    decision = decide_next_action(client, explanations)
    message = generate_message(client, decision)
    ai_analysis = _build_template_ai_analysis(client, decision, explanations)
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
        "ai_analysis": ai_analysis,
        "ml_signature": signature_data["ml_signature"],
        "ml_signature_fields": signature_data["ml_signature_fields"],
        "decision_policy_version": DECISION_POLICY_VERSION,
        "errors": errors,
    }


def run_bad_debts_agent(db: Session, msisdn: str) -> dict[str, Any] | None:
    started_at = datetime.utcnow()
    fallback_run_id = str(uuid4())
    try:
        client = _load_client(db, msisdn)
        if not client:
            return None
        signature_data = build_client_ml_signature(client)
        reusable = get_reusable_agent_run_response(db, msisdn, signature_data["ml_signature"])
        if reusable is not None:
            return reusable
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


def _priority_label(priority: Any) -> str:
    try:
        numeric = int(priority)
    except (TypeError, ValueError):
        return "Normal"
    return PRIORITY_BUSINESS_LABELS.get(numeric, "Normal")


def _tier_business_label(tier: str) -> str:
    if tier == "high":
        return "élevé"
    if tier == "medium":
        return "moyen"
    return "faible"


def _action_business_label(value: Any) -> str:
    return ACTION_BUSINESS_LABELS.get(str(value or ""), "Suivi routine")


def _build_template_ai_analysis(
    client: dict[str, Any],
    decision: dict[str, Any],
    explanations: dict[str, Any],
) -> dict[str, Any]:
    return build_deterministic_client_analysis(
        client,
        build_client_profile(client),
        explanations,
        decision,
    )


def _business_factor_labels(value: Any) -> list[str]:
    labels = {
        "AVG_CREDIT_AMOUNT": "Montant moyen crédité",
        "avg_credit_amount": "Montant moyen crédité",
        "never_repaid": "Aucun remboursement détecté",
        "reimburse_ratio": "Ratio de remboursement",
        "TOTAL_OUTSTANDING_AMOUNT": "Encours restant",
        "total_outstanding_amount": "Encours restant",
        "credit_intensity": "Fréquence d'utilisation SOS",
        "full_repayer": "Remboursement intégral observé",
        "debt_to_credit": "Dette rapportée au crédit",
        "NB_SOS": "Nombre d'usages SOS",
    }
    raw_items = value if isinstance(value, list) else [value] if value else []
    factors = []
    for item in raw_items:
        key = str(item.get("feature") or item.get("name") or "") if isinstance(item, dict) else str(item or "")
        label = labels.get(key)
        if label:
            factors.append(label)
    return factors


def _unique_non_empty(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text_value = str(value or "").strip()
        if not text_value or text_value in seen:
            continue
        seen.add(text_value)
        result.append(text_value)
    return result


def _format_optional(value: Any) -> str:
    if value is None or value == "":
        return "non disponible"
    try:
        return f"{float(value):.3f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(value)


def _format_amount(value: Any) -> str:
    numeric = _as_float(value)
    if numeric is None:
        return "0"
    if numeric.is_integer():
        return str(int(numeric))
    return f"{numeric:.2f}".rstrip("0").rstrip(".")


def _segment_business_label(value: Any) -> str:
    labels = {
        "DISCONNECTED": "Déconnecté",
        "SUSPENDED": "Suspendu",
        "ON-HOLD": "En attente",
        "Bon-payeur": "Bon payeur",
        "Standard": "Standard",
    }
    return labels.get(str(value or ""), "Segment non défini")


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


def _normalize_signature_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, (int, float, Decimal)):
        return round(float(value), 4)
    if isinstance(value, str):
        raw = value.strip()
        lowered = raw.lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        try:
            return round(float(raw), 4)
        except ValueError:
            return lowered
    return value


def _is_complete_agent_payload(payload: dict[str, Any]) -> bool:
    required_sections = ("profile", "explanations", "decision", "message", "ai_analysis")
    if any(not isinstance(payload.get(section), dict) or not payload.get(section) for section in required_sections):
        return False
    analysis = payload.get("ai_analysis") or {}
    required_text = ("business_summary", "decision_reasoning", "internal_note")
    if any(not str(analysis.get(key) or "").strip() for key in required_text):
        return False
    for key in ("key_risk_factors", "recommended_next_steps"):
        value = analysis.get(key)
        if not isinstance(value, list) or not value:
            return False
    return bool(payload.get("ml_signature"))


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
