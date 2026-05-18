from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from app.agents.state import AgentState
from app.services.bad_debts_agent_service import (
    build_deterministic_client_analysis,
    build_client_profile,
    build_explanations,
    compute_client_decision,
    decide_next_action,
    generate_message,
    log_agent_action,
    log_agent_run,
)

try:
    from app.core.config import settings
except Exception:
    settings = None


def effective_risk_tier(ml_outputs: dict[str, Any] | None) -> str:
    outputs = ml_outputs or {}
    risk_tier = _normalize_tier(outputs.get("risk_tier"))
    is_anomaly = bool(outputs.get("is_anomaly"))

    if is_anomaly and risk_tier == "low":
        return "medium"
    if is_anomaly and risk_tier == "medium":
        return "high"
    return risk_tier


def profiling_node(state: AgentState) -> AgentState:
    try:
        client = _client_from_state(state)
        profile = build_client_profile(client)
        return {"client": client, "profile": profile}
    except Exception as exc:
        return {"errors": [f"profiling_node: {exc}"], "profile": _fallback_profile(state)}


def explainability_node(state: AgentState) -> AgentState:
    try:
        client = _client_from_state(state)
        explanations = build_explanations(client)
        return {"client": client, "explanations": explanations}
    except Exception as exc:
        return {"errors": [f"explainability_node: {exc}"], "explanations": _fallback_explanations(state)}


def decision_node(state: AgentState) -> AgentState:
    try:
        client = _client_from_state(state)
        explanations = state.get("explanations") or {}
        decision = decide_next_action(client, explanations)
        decision = _normalize_decision_contract(client, decision)
        return {"client": client, "decision": decision}
    except Exception as exc:
        return {"errors": [f"decision_node: {exc}"], "decision": _fallback_decision(state)}


def message_generation_node(state: AgentState) -> AgentState:
    try:
        client = _client_from_state(state)
        decision = state.get("decision") or {}
        fallback_message = _normalize_message_contract(generate_message(client, decision))
        message = _generate_local_contact_message(client, decision, fallback_message)
    except Exception as exc:
        fallback_message = _fallback_message(state.get("decision") or {})
        return {
            "errors": [f"message_generation_node: {exc}"],
            "message": _lock_message_metadata(
                fallback_message,
                generated_by="template",
                llm_error=str(exc)[:180] or exc.__class__.__name__,
            ),
        }

    return {"message": _lock_message_metadata(message, generated_by=message.get("generated_by") or "deterministic_template")}


def ai_analysis_node(state: AgentState) -> AgentState:
    try:
        client = _client_from_state(state)
        decision = state.get("decision") or {}
        explanations = state.get("explanations") or {}
        profile = state.get("profile") or build_client_profile(client)
        analysis = build_deterministic_client_analysis(client, profile, explanations, decision)
        return {"ai_analysis": analysis}
    except Exception as exc:
        return {
            "errors": [f"ai_analysis_node: {exc}"],
            "ai_analysis": build_ai_analysis(_client_from_state(state), state.get("decision") or {}, state.get("explanations") or {}),
        }


def monitoring_node(state: AgentState) -> AgentState:
    db = state.get("db")
    decision = state.get("decision") or {}
    run_id = state.get("run_id") or ""
    msisdn = state.get("msisdn") or _client_from_state(state).get("msisdn") or ""
    existing_errors = [str(error) for error in (state.get("errors") or [])]

    if db is None:
        return {
            "action_id": None,
            "agent_run_id": None,
            "persisted": False,
            "monitoring": {
                "status": "memory_only",
                "summary": "Analyse préparée sans enregistrement persistant.",
                "action_type": decision.get("action_type"),
                "effective_tier": decision.get("effective_tier"),
            },
        }

    if state.get("client_found") is False and any("Client introuvable" in error for error in existing_errors):
        return {
            "action_id": None,
            "agent_run_id": None,
            "persisted": False,
            "monitoring": {
                "status": "client_not_found",
                "summary": "Aucune persistance effectuee car le client est introuvable.",
                "action_type": decision.get("action_type"),
                "effective_tier": decision.get("effective_tier"),
            },
        }

    errors: list[str] = []
    started_at = state.get("started_at") or datetime.utcnow()
    finished_at = datetime.utcnow()
    action_id = None
    agent_run_id = None

    try:
        logging_result = log_agent_action(db, msisdn, decision)
        action_id = logging_result.get("stored_action_id")
        decision = {
            **decision,
            "action_logged": bool(logging_result.get("action_logged")),
            "action_reused": bool(logging_result.get("action_reused")),
            "stored_action_id": action_id,
            "reused_action": logging_result.get("reused_action"),
        }
        if not logging_result.get("action_logged") and not logging_result.get("action_reused"):
            errors.append(logging_result.get("error") or "Action non journalisee.")
    except Exception as exc:
        errors.append(f"log_agent_action: {exc}")

    payload = _response_payload(state, decision, action_id, None)
    try:
        agent_run_id = log_agent_run(
            db,
            run_id=run_id,
            msisdn=msisdn,
            status="success" if not errors else "partial_success",
            action_id=action_id,
            effective_tier=decision.get("effective_tier"),
            anomaly_escalated=bool(decision.get("anomaly_escalated")),
            payload=payload,
            error_message="; ".join(errors) if errors else None,
            started_at=started_at,
            finished_at=finished_at,
        )
        if agent_run_id is None:
            errors.append("Run agent non journalise.")
    except Exception as exc:
        errors.append(f"log_agent_run: {exc}")

    return {
        "decision": decision,
        "action_id": action_id,
        "agent_run_id": agent_run_id,
        "persisted": agent_run_id is not None,
        "monitoring": {
            "status": "persisted" if agent_run_id is not None else "not_persisted",
            "action_type": decision.get("action_type"),
            "effective_tier": decision.get("effective_tier"),
        },
        "errors": errors,
    }


def _client_from_state(state: AgentState) -> dict[str, Any]:
    client = state.get("client") or state.get("raw_client")
    if client is not None:
        return _as_dict(client)

    ml_outputs = dict(state.get("ml_outputs") or {})
    features = dict(state.get("features") or {})
    return {
        **features,
        **ml_outputs,
        "msisdn": state.get("msisdn") or ml_outputs.get("msisdn") or features.get("msisdn"),
    }


def _normalize_decision_contract(client: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    action_type = decision.get("action_type") or decision.get("recommended_action") or "monitor_only"
    effective_tier_value = decision.get("effective_tier") or effective_risk_tier(client)
    safe_to_send = action_type != "monitor_only"
    recommendation = decision.get("recommendation") or decision.get("next_best_action") or decision.get("reason")
    return {
        **decision,
        "action_type": action_type,
        "recommended_action": action_type,
        "recommendation": recommendation,
        "effective_tier": _normalize_tier(effective_tier_value),
        "safe_to_send": safe_to_send,
    }


def _normalize_message_contract(message: dict[str, Any]) -> dict[str, Any]:
    content = message.get("content") or message.get("message_text") or ""
    return {
        **message,
        "contact_type": message.get("contact_type") or _contact_type_for_action(message.get("channel")),
        "title": message.get("title") or _contact_title_for_type(message.get("contact_type") or _contact_type_for_action(message.get("channel"))),
        "content": content,
        "message_text": content,
        "internal_notice": message.get("internal_notice") or _contact_notice(message.get("contact_type") or _contact_type_for_action(message.get("channel"))),
        "safe_to_send": bool(message.get("safe_to_send")),
        "generated_by": message.get("generated_by") or "deterministic_template",
        "llm_used": bool(message.get("llm_used")),
    }


def _generate_local_contact_message(
    client: dict[str, Any],
    decision: dict[str, Any],
    fallback_message: dict[str, Any],
) -> dict[str, Any]:
    action_type = str(decision.get("action_type") or decision.get("recommended_action") or "")
    if action_type != "sms_retention_offer":
        return fallback_message
    if not bool(client.get("is_anomaly")):
        return fallback_message
    if not settings or not bool(getattr(settings, "BAD_DEBTS_OLLAMA_ENABLED", False)):
        return fallback_message

    prompt = _contact_prompt(client, decision, fallback_message)
    primary_model = str(getattr(settings, "BAD_DEBTS_OLLAMA_MODEL", "") or "").strip() or None
    backup_model = str(getattr(settings, "BAD_DEBTS_OLLAMA_BACKUP_MODEL", "") or "").strip()
    generated = _call_contact_llm(prompt, primary_model)
    message = _build_contact_message(client, decision, fallback_message, generated)
    if _validate_contact_message(message, client, decision):
        return message
    if backup_model and backup_model != primary_model:
        generated = _call_contact_llm(prompt, backup_model)
        message = _build_contact_message(client, decision, fallback_message, generated)
        if _validate_contact_message(message, client, decision):
            return message
    return fallback_message


def _call_contact_llm(prompt: str, model_name: str | None) -> dict[str, Any] | None:
    try:
        from app.services.bad_debts_llm_report_service import call_ollama_json

        return call_ollama_json(prompt, model_name=model_name, num_predict=120)
    except Exception:
        return None


def _contact_prompt(client: dict[str, Any], decision: dict[str, Any], fallback_message: dict[str, Any]) -> str:
    debt = _as_float(client.get("total_outstanding_amount"))
    reimb = _as_float(client.get("avg_reimburse_ratio"))
    reimb_percent = reimb * 100 if reimb is not None and reimb <= 1 else reimb
    debt_text = _format_amount(debt) if debt is not None and debt > 0 else None
    expected_shape = (
        f"Bonjour, votre ligne fait l'objet d'un suivi de situation. Un solde à suivre de {debt_text} TND est identifié ; "
        "nous vous invitons à vérifier votre situation ou à contacter le service client pour plus d'informations."
        if debt_text
        else "Bonjour, votre ligne fait l'objet d'un suivi de situation. Certains indicateurs nécessitent une vérification ; "
        "nous vous invitons à vérifier votre situation ou à contacter le service client pour plus d'informations."
    )
    context = {
        "solde_autorise": debt_text,
        "taux_remboursement_autorise": round(reimb_percent, 2) if reimb_percent is not None else None,
        "segment_client": client.get("cluster_name") or client.get("state"),
        "situation": "suivi de situation avec indicateurs à vérifier",
    }
    return (
        "Tu rédiges un seul SMS client court et neutre en français. "
        "Réponds uniquement avec un objet contenant la clé message_text. "
        "Copie presque ce modèle, en l'adaptant seulement au solde autorisé: "
        f"\"{expected_shape}\" "
        "N'écris pas les noms des clés du contexte. N'invente aucun chiffre ni historique. "
        "Si solde_autorise vaut null, ne parle pas de solde à suivre. "
        "Si taux_remboursement_autorise est supérieur ou égal à 95, ne parle pas de remboursement faible. "
        "Ne mentionne pas anomalie, risque, score ML, défaut, urgence, menace ou recouvrement. "
        "Ne dis jamais que le SMS a été envoyé. Ne promets aucune solution. "
        "Interdits: anomalie détectée, risque de défaut, mauvais payeur, dette urgente, régler dans les brefs délais, "
        "rester actif, suspension, sanction, menace, poursuite, contentieux, recouvrement, remise, réduction, bonus, "
        "cadeau, offre commerciale, plan d'apurement, offre de restructuration, score ML, Qwen, IA, JSON, backend, API. "
        f"Contexte:{json.dumps(context, ensure_ascii=False, default=str)}"
    )


def _build_contact_message(
    client: dict[str, Any],
    decision: dict[str, Any],
    fallback_message: dict[str, Any],
    generated: dict[str, Any] | None,
) -> dict[str, Any]:
    content = _clean_generated_sms(str((generated or {}).get("message_text") or "").strip(), client)
    if not content:
        return fallback_message
    action_type = str(decision.get("action_type") or decision.get("recommended_action") or "")
    contact_type, title, safe_to_send = _contact_contract(action_type, bool(client.get("is_anomaly")))
    return {
        **fallback_message,
        "contact_type": contact_type,
        "title": title,
        "channel": "sms" if contact_type in {"preventive_sms", "preventive_sms_ai"} else "call" if contact_type == "call_script" else "monitoring",
        "message_text": content,
        "content": content,
        "language": "fr",
        "internal_notice": _contact_notice(contact_type),
        "safe_to_send": safe_to_send,
        "generated_by": "local_llm",
        "llm_used": True,
    }


def _clean_generated_sms(text: str, client: dict[str, Any]) -> str:
    cleaned = str(text or "").strip().strip('"').strip("'")
    if not cleaned:
        return ""
    cleaned = re.sub(r"^message_text\s*[:=]\s*", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = cleaned.replace("signal_atypique", "certains indicateurs")
    cleaned = re.sub(r"\bsignal atypique\b", "certains indicateurs", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\batypique détecté\b", "nécessitent une vérification", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\batypique detecte\b", "nécessitent une vérification", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bdétecté\b", "identifié", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bdetecte\b", "identifié", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace("_", " ")
    debt = _as_float(client.get("total_outstanding_amount"))
    if debt is not None and debt == 0:
        cleaned = re.sub(r"[^.?!;]*\bsolde à suivre\b[^.?!;]*[.?!;]?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
        if not cleaned or len(cleaned) < 25:
            cleaned = (
                "Bonjour, votre ligne fait l'objet d'un suivi de situation. "
                "Certains indicateurs nécessitent une vérification ; nous vous invitons à vérifier votre situation "
                "ou à contacter le service client pour plus d'informations."
            )
    return cleaned


def _contact_contract(action_type: str, has_anomaly: bool = False) -> tuple[str, str, bool]:
    if action_type == "call_center_priority":
        return "call_script", "Script conseiller", False
    if action_type == "sms_retention_offer":
        if has_anomaly:
            return "preventive_sms_ai", "SMS personnalisé proposé", True
        return "preventive_sms", "SMS personnalisé proposé", True
    return "monitoring_note", "Note de suivi", False


def _contact_type_for_action(channel: Any) -> str:
    if channel == "call":
        return "call_script"
    if channel == "sms":
        return "preventive_sms"
    return "monitoring_note"


def _contact_title_for_type(contact_type: Any) -> str:
    if contact_type == "call_script":
        return "Script conseiller"
    if contact_type in {"preventive_sms", "preventive_sms_ai"}:
        return "SMS personnalisé proposé"
    return "Note de suivi"


def _contact_notice(contact_type: Any) -> str:
    if contact_type in {"preventive_sms", "preventive_sms_ai"}:
        return "Proposition interne à valider avant envoi."
    return "Proposition interne non envoyée automatiquement."


def _validate_contact_message(message: dict[str, Any], client: dict[str, Any], decision: dict[str, Any]) -> bool:
    text = str(message.get("message_text") or message.get("content") or "").strip()
    if not text or len(text) > 420 or _contains_forbidden_contact_text(text):
        return False
    action_type = str(decision.get("action_type") or decision.get("recommended_action") or "")
    expected_contact_type, expected_title, expected_safe = _contact_contract(action_type, bool(client.get("is_anomaly")))
    if message.get("contact_type") != expected_contact_type or message.get("title") != expected_title:
        return False
    if bool(message.get("safe_to_send")) != expected_safe:
        return False
    lowered = text.lower()
    if action_type == "call_center_priority" and any(term in lowered for term in ("sms", "message envoyé", "envoyé")):
        return False
    if action_type == "sms_retention_offer" and any(term in lowered for term in ("appel prioritaire", "urgence", "critique")):
        return False
    if action_type == "monitor_only" and any(term in lowered for term in ("urgent", "critique", "prioritaire")):
        return False
    if "_" in text or "anomal" in lowered or "score ml" in lowered or "signal_atypique" in lowered or "atypique détecté" in lowered or "atypique detecte" in lowered:
        return False
    debt = _as_float(client.get("total_outstanding_amount"))
    if debt is not None and debt == 0 and any(term in lowered for term in ("dette active", "encours actif", "impayé actif", "montant à recouvrer", "solde à suivre")):
        return False
    reimb = _as_float(client.get("avg_reimburse_ratio"))
    reimb_percent = reimb * 100 if reimb is not None and reimb <= 1 else reimb
    if reimb_percent is not None and reimb_percent >= 95 and any(term in lowered for term in ("remboursement faible", "remboursement dégradé", "moins régulier", "baisse de remboursement")):
        return False
    if not _numbers_allowed(text, client, decision):
        return False
    if any(term in lowered for term in ("a été envoyé", "sms envoyé", "appel effectué", "conseiller a appelé")):
        return False
    return True


def _contains_forbidden_contact_text(text: str) -> bool:
    lowered = str(text or "").lower()
    forbidden = (
        "plan d'apurement",
        "plan d’apurement",
        "offre de restructuration",
        "anomalie détectée",
        "risque de défaut",
        "mauvais payeur",
        "dette urgente",
        "régler dans les brefs délais",
        "regler dans les brefs delais",
        "rester actif",
        "suspension",
        "remise",
        "réduction",
        "reduction",
        "bonus",
        "cadeau",
        "offre commerciale",
        "sanction",
        "menace",
        "contentieux",
        "poursuite",
        "recouvrement agressif",
        "recouvrement",
        "score ml",
        "signal_atypique",
        "atypique détecté",
        "atypique detecte",
        "fraude",
        "blacklist",
        "qwen",
        "ollama",
        "api",
        "json",
        "backend",
        "frontend",
        "modèle ia",
        "llm",
        "fallback",
    )
    return any(term in lowered for term in forbidden) or bool(re.search(r"\bia\b", lowered)) or _contains_complete_msisdn(lowered)


def _numbers_allowed(text: str, client: dict[str, Any], decision: dict[str, Any]) -> bool:
    allowed: set[str] = {"1", "2", "3", "4"}
    for value in (
        client.get("final_risk_score"),
        client.get("total_outstanding_amount"),
        client.get("avg_reimburse_ratio"),
        client.get("debt_to_credit"),
        client.get("nb_sos"),
        decision.get("priority"),
    ):
        _add_allowed_number(allowed, value)
    for raw in re.findall(r"\d+(?:[\s\u202f]\d{3})*(?:[.,]\d+)?|\d+", str(text or "")):
        normalized = raw.replace("\u202f", "").replace(" ", "").replace(",", ".")
        if normalized.startswith("216") and len(normalized) >= 8:
            return False
        if normalized not in allowed:
            return False
    return True


def _add_allowed_number(allowed: set[str], value: Any) -> None:
    if value is None or value == "":
        return
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return
    if numeric.is_integer():
        allowed.add(str(int(numeric)))
    allowed.add(f"{numeric:.3f}".rstrip("0").rstrip("."))
    allowed.add(str(round(numeric, 3)).rstrip("0").rstrip("."))


def _contains_complete_msisdn(text: str) -> bool:
    return bool(re.search(r"\b216\d{5,9}\b", str(text or ""))) or bool(re.search(r"\b\d{8,12}\b", str(text or "")))


def _fallback_profile(state: AgentState) -> dict[str, Any]:
    client = _client_from_state(state)
    return {
        "msisdn": client.get("msisdn"),
        "state": client.get("state"),
        "cluster_name": client.get("cluster_name"),
        "risk_tier": _normalize_tier(client.get("risk_tier")),
        "risk_label": client.get("risk_label"),
        "final_risk_score": _as_float(client.get("final_risk_score")),
        "is_anomaly": bool(client.get("is_anomaly")),
    }


def _fallback_explanations(state: AgentState) -> dict[str, Any]:
    client = _client_from_state(state)
    rules = []
    if bool(client.get("is_anomaly")):
        rules.append("Comportement atypique detecte")
    if _is_sensitive_client(client):
        rules.append("Client sensible detecte")
    return {"primary_factors": [], "business_rules": rules, "explanation_text": "; ".join(rules)}


def _fallback_decision(state: AgentState) -> dict[str, Any]:
    client = _client_from_state(state)
    decision = compute_client_decision(client)
    action_type = decision["recommended_action"]
    return {
        **decision,
        "action_type": action_type,
        "recommendation": decision["next_best_action"],
        "safe_to_send": action_type != "monitor_only",
    }


def build_ai_analysis(
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


def _normalize_ai_analysis(value: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    return {
        "business_summary": str(source.get("business_summary") or fallback.get("business_summary") or ""),
        "decision_reasoning": str(source.get("decision_reasoning") or fallback.get("decision_reasoning") or ""),
        "key_risk_factors": _string_list(source.get("key_risk_factors") or fallback.get("key_risk_factors")),
        "recommended_next_steps": _string_list(source.get("recommended_next_steps") or fallback.get("recommended_next_steps")),
        "internal_note": str(source.get("internal_note") or fallback.get("internal_note") or ""),
    }


def _fallback_message(decision: dict[str, Any]) -> dict[str, Any]:
    action_type = decision.get("action_type")
    if not decision.get("safe_to_send"):
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
    if action_type == "call_center_priority":
        content = "Contacter le client via le centre de relation client afin de qualifier la situation, vérifier les informations disponibles et orienter le suivi selon les règles métier internes."
        return {"contact_type": "call_script", "title": "Script conseiller", "channel": "call", "message_text": content, "content": content, "language": "fr", "internal_notice": "Proposition interne non envoyée automatiquement.", "safe_to_send": False, "generated_by": "deterministic_template", "llm_used": False}
    if action_type == "sms_retention_offer":
        content = "Bonjour, un suivi de votre ligne est recommandé. Merci de vérifier votre situation ou de contacter le service client pour plus d’informations."
        return {"contact_type": "preventive_sms", "title": "SMS personnalisé proposé", "channel": "sms", "message_text": content, "content": content, "language": "fr", "internal_notice": "Proposition interne à valider avant envoi.", "safe_to_send": True, "generated_by": "deterministic_template", "llm_used": False}
    content = "Aucune action immédiate n’est recommandée. Conserver un suivi périodique lors des prochains imports."
    return {"contact_type": "monitoring_note", "title": "Note de suivi", "channel": "monitoring", "message_text": content, "content": content, "language": "fr", "internal_notice": "Proposition interne non envoyée automatiquement.", "safe_to_send": False, "generated_by": "deterministic_template", "llm_used": False}


def _response_payload(
    state: AgentState,
    decision: dict[str, Any],
    action_id: int | None,
    agent_run_id: int | None,
) -> dict[str, Any]:
    message = state.get("message") or {}
    return {
        "orchestrator": "langgraph",
        "run_id": state.get("run_id"),
        "msisdn": state.get("msisdn"),
        "profile": state.get("profile") or {},
        "explanations": state.get("explanations") or {},
        "decision": decision,
        "message": message,
        "ai_analysis": state.get("ai_analysis") or {},
        "ml_signature": state.get("ml_signature") or "",
        "ml_signature_fields": state.get("ml_signature_fields") or {},
        "decision_policy_version": state.get("decision_policy_version") or "",
        "action_id": action_id,
        "agent_run_id": agent_run_id,
        "llm_used": bool(message.get("llm_used")),
        "generated_by": message.get("generated_by") or "template",
        "llm_model": message.get("llm_model"),
        "llm_error": message.get("llm_error"),
        "llm_duration_ms": message.get("llm_duration_ms"),
        "llm_cache_hit": bool(message.get("llm_cache_hit")),
        "fallback_to_template": bool(message.get("fallback_to_template")),
        "hallucination_detected": bool(message.get("hallucination_detected")),
        "decision_locked": True,
        "action_type": decision.get("action_type") or decision.get("recommended_action"),
        "effective_tier": decision.get("effective_tier"),
        "anomaly_escalated": bool(decision.get("anomaly_escalated")),
        "errors": state.get("errors") or [],
    }


def _lock_message_metadata(
    message: dict[str, Any],
    *,
    generated_by: str,
    llm_model: Any = None,
    llm_error: Any = None,
    llm_cache_hit: bool = False,
    llm_duration_ms: Any = 0,
    fallback_to_template: bool | None = None,
    hallucination_detected: bool = False,
) -> dict[str, Any]:
    used_llm = generated_by in {"llm", "llm_cache", "local_llm"}
    used_template = not used_llm
    return {
        **message,
        "generated_by": generated_by,
        "llm_used": used_llm,
        "llm_model": llm_model if used_llm else None,
        "llm_error": None if used_llm else llm_error,
        "llm_cache_hit": bool(llm_cache_hit),
        "llm_duration_ms": int(llm_duration_ms or 0),
        "fallback_to_template": bool(used_template if fallback_to_template is None else fallback_to_template),
        "hallucination_detected": bool(hallucination_detected),
        "decision_locked": True,
    }


def _risk_label(value: Any) -> str:
    tier = _normalize_tier(value)
    if tier == "high":
        return "élevé"
    if tier == "medium":
        return "moyen"
    return "faible"


def _action_label(value: Any) -> str:
    labels = {
        "call_center_priority": "Appel prioritaire centre de relation client",
        "sms_retention_offer": "SMS personnalisé",
        "monitor_only": "Suivi routine",
    }
    return labels.get(str(value or ""), "Suivi routine")


def _priority_label(value: Any) -> str:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return "Normal"
    if numeric == 1:
        return "Très urgent"
    if numeric == 2:
        return "Urgent"
    if numeric == 4:
        return "Normal"
    return "Normal"


def _segment_label(value: Any) -> str:
    labels = {
        "DISCONNECTED": "Déconnecté",
        "SUSPENDED": "Suspendu",
        "ON-HOLD": "En attente",
        "Bon-payeur": "Bon payeur",
        "Standard": "Standard",
    }
    return labels.get(str(value or ""), "Segment non défini")


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
    factors = []
    raw_items = value if isinstance(value, list) else [value] if value else []
    for item in raw_items:
        if isinstance(item, dict):
            key = str(item.get("feature") or item.get("name") or "")
        else:
            key = str(item or "")
        label = labels.get(key)
        if label:
            factors.append(label)
    return factors


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if value:
        return [str(value)]
    return []


def _format_optional(value: Any) -> str:
    if value is None or value == "":
        return "non disponible"
    try:
        return f"{float(value):.3f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(value)


def _is_sensitive_client(client: dict[str, Any]) -> bool:
    return (
        "disconnected" in _lower_text(client.get("state"))
        or "disconnected" in _lower_text(client.get("cluster_name"))
        or "disconnected" in _lower_text(client.get("risk_label"))
        or "blacklist" in _lower_text(client.get("risk_label"))
    )


def _normalize_tier(value: Any) -> str:
    tier = str(value or "low").strip().lower()
    return tier if tier in {"low", "medium", "high"} else "low"


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "_mapping"):
        return dict(value._mapping)
    try:
        return dict(value)
    except Exception:
        return {
            key: getattr(value, key)
            for key in dir(value)
            if not key.startswith("_") and not callable(getattr(value, key, None))
        }


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_amount(value: Any) -> str:
    numeric = _as_float(value)
    if numeric is None:
        return "0"
    if numeric.is_integer():
        return str(int(numeric))
    return f"{numeric:.2f}".rstrip("0").rstrip(".")


def _lower_text(value: Any) -> str:
    return str(value or "").strip().lower()
