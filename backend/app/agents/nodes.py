from __future__ import annotations

import os
import json
import time
from collections import OrderedDict
from datetime import datetime
from typing import Any

from app.agents.state import AgentState
from app.services.bad_debts_agent_service import (
    build_client_profile,
    build_explanations,
    decide_next_action,
    generate_message,
    log_agent_action,
    log_agent_run,
)

try:
    from app.core.config import settings
except Exception:
    settings = None


LLM_REWRITE_CACHE_MAX_SIZE = 256
_LLM_REWRITE_CACHE: OrderedDict[str, str] = OrderedDict()


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

    if not fallback_message.get("safe_to_send") or decision.get("action_type") == "recovery_review":
        return {"message": _lock_message_metadata(fallback_message, generated_by="template")}

    if not state.get("enable_llm", True):
        return {"message": _lock_message_metadata(fallback_message, generated_by="template")}

    llm_context = {
        "profile": _client_llm_profile(client),
        "decision": _decision_llm_context(decision),
        "explanations": _explanations_llm_context(state.get("explanations") or {}),
        "template_message": fallback_message.get("content") or "",
        "channel": fallback_message.get("channel"),
        "safe_to_send": fallback_message.get("safe_to_send"),
    }
    llm_result = safe_llm_rewrite_recommendation(llm_context)
    if llm_result.get("content"):
        content = str(llm_result["content"])
        is_valid, rejection_reason = validate_llm_recommendation(
            content,
            decision,
            fallback_message,
        )
        if not is_valid:
            message = _lock_message_metadata(
                fallback_message,
                generated_by="template",
                llm_error=f"LLM output rejected by guard: {rejection_reason}",
                llm_duration_ms=llm_result.get("llm_duration_ms"),
                fallback_to_template=True,
                hallucination_detected=True,
            )
            return {
                "message": message,
                "errors": [message["llm_error"]],
            }
        return {
            "message": _lock_message_metadata(
                {**fallback_message, "content": content, "message_text": content},
                generated_by="llm_cache" if llm_result.get("llm_cache_hit") else "llm",
                llm_model=llm_result.get("llm_model"),
                llm_cache_hit=bool(llm_result.get("llm_cache_hit")),
                llm_duration_ms=llm_result.get("llm_duration_ms"),
            )
        }

    message = _lock_message_metadata(
        fallback_message,
        generated_by="template",
        llm_error=llm_result.get("llm_error"),
        llm_duration_ms=llm_result.get("llm_duration_ms"),
    )
    return {"message": message}


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
                "summary": "Execution LangGraph preparee sans persistance PostgreSQL.",
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

    if _is_sensitive_client(client):
        action_type = "recovery_review"
        decision = {
            **decision,
            "recommended_action": action_type,
            "action_type": action_type,
            "priority": 1,
            "next_best_action": "Verification recouvrement et traitement prioritaire",
            "effective_tier": effective_tier_value,
        }

    safe_to_send = action_type not in {"monitor_only", "recovery_review"}
    recommendation = decision.get("recommendation") or decision.get("next_best_action") or decision.get("reason")
    return {
        **decision,
        "action_type": action_type,
        "recommendation": recommendation,
        "effective_tier": _normalize_tier(effective_tier_value),
        "safe_to_send": safe_to_send,
    }


def _normalize_message_contract(message: dict[str, Any]) -> dict[str, Any]:
    content = message.get("content") or message.get("message_text") or ""
    return {
        **message,
        "content": content,
        "message_text": content,
        "safe_to_send": bool(message.get("safe_to_send")),
        "generated_by": message.get("generated_by") or "template",
    }


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
    effective_tier_value = effective_risk_tier(client)
    if _is_sensitive_client(client):
        action_type, priority, recommendation, safe_to_send = (
            "recovery_review",
            1,
            "Verification recouvrement et traitement prioritaire",
            False,
        )
    elif effective_tier_value == "high":
        action_type, priority, recommendation, safe_to_send = (
            "call_center_priority",
            1,
            "Contact prioritaire par l'equipe recouvrement",
            True,
        )
    elif effective_tier_value == "medium":
        action_type, priority, recommendation, safe_to_send = (
            "sms_reminder",
            2,
            "Rappel SMS de regularisation",
            True,
        )
    else:
        action_type, priority, recommendation, safe_to_send = (
            "monitor_only",
            4,
            "Surveillance simple sans action immediate",
            False,
        )
    return {
        "action_type": action_type,
        "priority": priority,
        "recommendation": recommendation,
        "effective_tier": effective_tier_value,
        "anomaly_escalated": effective_tier_value != _normalize_tier(client.get("risk_tier")),
        "safe_to_send": safe_to_send,
    }


def _fallback_message(decision: dict[str, Any]) -> dict[str, Any]:
    action_type = decision.get("action_type")
    if not decision.get("safe_to_send") or action_type == "recovery_review":
        return {
            "channel": "internal_review",
            "message_text": "Traitement interne recommande avant toute communication client.",
            "content": "Traitement interne recommande avant toute communication client.",
            "language": "fr",
            "safe_to_send": False,
            "generated_by": "template",
        }
    if action_type == "call_center_priority":
        content = "Contact prioritaire recommande pour regulariser le solde client."
        return {"channel": "call", "message_text": content, "content": content, "language": "fr", "safe_to_send": True}
    if action_type == "sms_reminder":
        content = "Bonjour, merci de regulariser votre solde via votre espace client Tunisie Telecom."
        return {"channel": "sms", "message_text": content, "content": content, "language": "fr", "safe_to_send": True}
    content = "Surveillance simple recommandee."
    return {"channel": "monitoring", "message_text": content, "content": content, "language": "fr", "safe_to_send": False}


def is_llm_available() -> bool:
    return _llm_enabled()


def safe_llm_rewrite_recommendation(context: dict[str, Any]) -> dict[str, Any]:
    model_name = str(_setting_value("OPENAI_MODEL", "gpt-4o-mini"))
    if not is_llm_available():
        return {
            "content": None,
            "llm_used": False,
            "llm_model": None,
            "llm_error": "LLM desactive ou cle API absente.",
            "llm_cache_hit": False,
            "llm_duration_ms": 0,
        }
    cache_key = _llm_cache_key(model_name, context)
    cached = _LLM_REWRITE_CACHE.get(cache_key)
    if cached is not None:
        _LLM_REWRITE_CACHE.move_to_end(cache_key)
        return {
            "content": cached,
            "llm_used": True,
            "llm_model": model_name,
            "llm_error": None,
            "llm_cache_hit": True,
            "llm_duration_ms": 0,
        }
    started = time.perf_counter()
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=model_name,
            api_key=_setting_value("OPENAI_API_KEY"),
            temperature=0.2,
            timeout=int(_setting_value("LLM_TIMEOUT_SECONDS", 12)),
            max_tokens=int(_setting_value("LLM_MAX_TOKENS", 220)),
        )
        response = llm.invoke(
            [
                SystemMessage(
                    content=(
                        "Tu es un assistant metier pour une plateforme interne Tunisie Telecom. "
                        "Tu dois reformuler la recommandation suivante en francais professionnel, clair et concis. "
                        "Ne modifie jamais l'action decidee, le niveau de risque, la priorite, le canal ou safe_to_send. "
                        "N'invente aucune donnee. "
                        "Si safe_to_send=false, la recommandation doit rester interne et ne doit pas etre formulee comme un message envoye au client. "
                        "Reponds uniquement avec le texte reformule."
                    )
                ),
                HumanMessage(content=json.dumps(context, ensure_ascii=False, default=str)),
            ]
        )
        content = str(getattr(response, "content", "") or "").strip()
        duration_ms = _duration_ms(started)
        if content:
            _cache_llm_rewrite(cache_key, content)
        return {
            "content": content or None,
            "llm_used": bool(content),
            "llm_model": model_name if content else None,
            "llm_error": None if content else "Reponse LLM vide.",
            "llm_cache_hit": False,
            "llm_duration_ms": duration_ms,
        }
    except Exception as exc:
        return {
            "content": None,
            "llm_used": False,
            "llm_model": None,
            "llm_error": str(exc)[:180] or exc.__class__.__name__,
            "llm_cache_hit": False,
            "llm_duration_ms": _duration_ms(started),
        }


def safe_llm_generate_batch_summary(context: dict[str, Any]) -> dict[str, Any]:
    if not is_llm_available():
        return {
            "summary": None,
            "recommendations": None,
            "ai_summary_used": False,
            "llm_model": None,
            "llm_error": "LLM desactive ou cle API absente.",
            "ai_summary_duration_ms": 0,
        }
    started = time.perf_counter()
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI

        model_name = _setting_value("OPENAI_MODEL", "gpt-4o-mini")
        llm = ChatOpenAI(
            model=model_name,
            api_key=_setting_value("OPENAI_API_KEY"),
            temperature=0.2,
            timeout=int(_setting_value("LLM_TIMEOUT_SECONDS", 12)),
            max_tokens=int(_setting_value("LLM_MAX_TOKENS", 220)),
        )
        response = llm.invoke(
            [
                SystemMessage(
                    content=(
                        "Tu es un assistant d'aide a la decision pour une plateforme interne Tunisie Telecom. "
                        "A partir des KPIs batch ci-dessous, redige une synthese executive courte et des recommandations metier. "
                        "Ne modifie pas les chiffres. N'invente pas de donnees. Ne cite pas d'informations absentes. "
                        "Le ton doit etre professionnel, oriente recouvrement et priorisation operationnelle. "
                        "Reponds uniquement avec un JSON strict: {\"summary\":\"...\",\"recommendations\":\"...\"}."
                    )
                ),
                HumanMessage(content=json.dumps(context, ensure_ascii=False, default=str)),
            ]
        )
        raw_content = str(getattr(response, "content", "") or "").strip()
        parsed = json.loads(raw_content)
        summary = str(parsed.get("summary") or "").strip()
        recommendations = str(parsed.get("recommendations") or "").strip()
        if not summary or not recommendations:
            raise ValueError("JSON LLM incomplet")
        is_valid, rejection_reason = validate_llm_batch_summary(summary, recommendations, context)
        if not is_valid:
            raise ValueError(f"LLM batch output rejected by guard: {rejection_reason}")
        return {
            "summary": summary,
            "recommendations": recommendations,
            "ai_summary_used": True,
            "llm_model": model_name,
            "llm_error": None,
            "ai_summary_duration_ms": _duration_ms(started),
        }
    except Exception as exc:
        return {
            "summary": None,
            "recommendations": None,
            "ai_summary_used": False,
            "llm_model": None,
            "llm_error": str(exc)[:180] or exc.__class__.__name__,
            "ai_summary_duration_ms": _duration_ms(started),
        }


def validate_llm_recommendation(
    text: str,
    decision: dict[str, Any],
    template_message: dict[str, Any],
) -> tuple[bool, str | None]:
    content = str(text or "").strip()
    lowered = content.lower()
    if not content:
        return False, "empty output"
    if len(content) < 12:
        return False, "too short"
    if len(content) > 600:
        return False, "too long"

    safe_to_send = bool(decision.get("safe_to_send"))
    channel = str(template_message.get("channel") or "").lower()
    action_type = str(decision.get("action_type") or decision.get("recommended_action") or "").lower()
    effective_tier = str(decision.get("effective_tier") or "").lower()

    if not safe_to_send:
        forbidden_client_terms = (
            "cher client",
            "chere cliente",
            "veuillez regulariser",
            "veuillez régulariser",
            "votre ligne",
            "nous vous invitons a payer",
            "nous vous invitons à payer",
        )
        if any(term in lowered for term in forbidden_client_terms):
            return False, "sensitive internal action phrased as client message"

    forbidden_promises = ("remise", "bonus", "offre", "reduction", "réduction", "annulation de dette")
    if any(term in lowered for term in forbidden_promises):
        return False, "unauthorized commercial promise"

    if channel == "internal_review" and ("sms" in lowered or "envoyer" in lowered):
        return False, "channel changed"
    if action_type == "monitor_only" and ("appel" in lowered or "sms" in lowered):
        return False, "action changed"
    if effective_tier == "high" and ("risque faible" in lowered or "faible risque" in lowered):
        return False, "risk tier changed"
    return True, None


def validate_llm_batch_summary(
    summary: str,
    recommendations: str,
    context: dict[str, Any],
) -> tuple[bool, str | None]:
    combined = f"{summary}\n{recommendations}".strip()
    lowered = combined.lower()
    if not summary.strip() or not recommendations.strip():
        return False, "missing summary or recommendations"
    if len(summary) > 900 or len(recommendations) > 900:
        return False, "too long"
    forbidden_promises = ("remise", "bonus", "offre commerciale", "reduction", "réduction", "annulation de dette")
    if any(term in lowered for term in forbidden_promises):
        return False, "unauthorized commercial promise"
    if _contains_full_msisdn(combined):
        return False, "full msisdn detected"

    allowed_numbers = {str(value) for key, value in context.items() if isinstance(value, int)}
    allowed_numbers.update(str(value) for value in (context.get("top_action_types") or {}).values())
    mentioned_numbers = set(_extract_numbers(combined))
    unexpected_numbers = {number for number in mentioned_numbers if number not in allowed_numbers and len(number) <= 4}
    if unexpected_numbers:
        return False, "invented number"
    return True, None


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


def _llm_enabled() -> bool:
    return _setting_bool("ENABLE_LLM_AGENT", False) and bool(_setting_value("OPENAI_API_KEY"))


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
    used_llm = generated_by in {"llm", "llm_cache"}
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


def _client_llm_profile(client: dict[str, Any]) -> dict[str, Any]:
    return {
        "risk_tier": client.get("risk_tier"),
        "risk_label": client.get("risk_label"),
        "cluster_name": client.get("cluster_name"),
        "state": client.get("state"),
        "is_anomaly": bool(client.get("is_anomaly")),
        "final_risk_score": client.get("final_risk_score"),
    }


def _decision_llm_context(decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "action_type": decision.get("action_type") or decision.get("recommended_action"),
        "effective_tier": decision.get("effective_tier"),
        "priority": decision.get("priority"),
        "safe_to_send": bool(decision.get("safe_to_send")),
        "recommendation": decision.get("recommendation") or decision.get("next_best_action"),
        "anomaly_escalated": bool(decision.get("anomaly_escalated")),
    }


def _explanations_llm_context(explanations: dict[str, Any]) -> dict[str, Any]:
    return {
        "business_rules": (explanations.get("business_rules") or [])[:5],
        "top_drivers": (explanations.get("primary_factors") or explanations.get("top_drivers") or [])[:3],
    }


def _setting_value(name: str, default: Any = None) -> Any:
    if settings is not None:
        value = getattr(settings, name, None)
        if value is not None:
            return value
    return os.getenv(name, default)


def _setting_bool(name: str, default: bool = False) -> bool:
    value = _setting_value(name, default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _llm_cache_key(model_name: str, context: dict[str, Any]) -> str:
    decision = context.get("decision") or {}
    explanations = context.get("explanations") or {}
    relevant = {
        "model": model_name,
        "action_type": decision.get("action_type"),
        "priority": decision.get("priority"),
        "effective_tier": decision.get("effective_tier"),
        "safe_to_send": decision.get("safe_to_send"),
        "channel": context.get("channel"),
        "template_message": context.get("template_message"),
        "business_rules": explanations.get("business_rules"),
        "top_drivers": explanations.get("top_drivers"),
    }
    return json.dumps(relevant, ensure_ascii=False, sort_keys=True, default=str)


def _cache_llm_rewrite(cache_key: str, content: str) -> None:
    _LLM_REWRITE_CACHE[cache_key] = content
    _LLM_REWRITE_CACHE.move_to_end(cache_key)
    while len(_LLM_REWRITE_CACHE) > LLM_REWRITE_CACHE_MAX_SIZE:
        _LLM_REWRITE_CACHE.popitem(last=False)


def _duration_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))


def _contains_full_msisdn(text: str) -> bool:
    return any(len(number) >= 8 and number.startswith("216") for number in _extract_numbers(text))


def _extract_numbers(text: str) -> list[str]:
    numbers: list[str] = []
    current = []
    for char in text:
        if char.isdigit():
            current.append(char)
        elif current:
            numbers.append("".join(current))
            current = []
    if current:
        numbers.append("".join(current))
    return numbers


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


def _lower_text(value: Any) -> str:
    return str(value or "").strip().lower()
