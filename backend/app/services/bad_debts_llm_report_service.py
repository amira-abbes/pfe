from __future__ import annotations

"""
Le moteur de rédaction IA Bad Debts utilise un modèle local via Ollama. 
Le modèle retenu pour l'environnement de démonstration est qwen2.5:7b, choisi après benchmark comparatif avec Mistral-Nemo 12B sur 21 scénarios de filtres. 
Les KPIs et décisions sont calculés par Python/PostgreSQL ; le modèle local rédige uniquement le rapport, puis Python valide la sortie.
"""

import json
import re
import time
from datetime import datetime, timezone
from typing import Any

import requests
from requests import RequestException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.bad_debts_agent_service import (
    build_client_profile,
    build_deterministic_client_analysis,
    build_explanations,
    decide_next_action,
    generate_message,
)
from app.services.bad_debts_service import BadDebtsService


TECHNICAL_FORBIDDEN_TERMS = (
    "langgraph",
    "llm",
    "openai",
    "ollama",
    "gpt",
    "fastapi",
    "postgresql",
    "api",
    "json",
    "backend",
    "frontend",
    "prompt",
    "token",
    "n8n",
    "payload",
    "run_id",
    "action_id",
    "agent_run_id",
)

BUSINESS_FORBIDDEN_TERMS = (
    "fraude",
    "frauduleux",
    "mauvais payeur",
    "refuse de payer",
    "client malhonnête",
    "client malhonnete",
    "poursuite judiciaire",
    "blacklist",
    "menace",
    "harcèlement",
    "harcelement",
    "résiliation",
    "resiliation",
    "remise",
    "réduction",
    "reduction",
    "bonus",
    "cadeau",
    "offre commerciale",
    "annulation de dette",
    "effacement",
    "promotion",
    "avantage commercial",
    "sanction",
    "contentieux",
    "poursuite",
    "accusation",
    "plan d'apurement",
    "plan d’apurement",
    "offre de restructuration",
    "recouvrement agressif",
)

REPORT_REQUIRED_FIELDS = (
    "title",
    "case_reading",
    "signals_interpretation",
    "operational_risk",
    "verification_points",
    "argued_recommendation",
    "sms_proposal",
    "manager_summary",
    "confidence",
)

_LAST_LOCAL_MODEL_ERROR = ""
_LAST_LOCAL_MODEL_SECONDS: float | None = None


def generate_client_llm_report(db: Session, msisdn: str) -> dict[str, Any] | None:
    context = build_client_report_context(msisdn, db)
    if context is None:
        return None

    report_source = "deterministic_fallback"
    report = fallback_client_report(context)
    if _client_report_enabled():
        prompt = _client_report_prompt(context)
        primary_model = str(settings.BAD_DEBTS_OLLAMA_MODEL or "").strip()
        backup_model = str(settings.BAD_DEBTS_OLLAMA_BACKUP_MODEL or "").strip()
        generated = call_ollama_json(prompt, model_name=primary_model, num_predict=320)
        normalized = _normalize_report(generated or {}, context) if generated else None
        if not (normalized and validate_client_llm_report(normalized, context)) and backup_model and backup_model != primary_model:
            generated = call_ollama_json(prompt, model_name=backup_model, num_predict=320)
            normalized = _normalize_report(generated or {}, context) if generated else None
        if normalized and validate_client_llm_report(normalized, context):
            report = normalized
            report_source = "local_llm"

    return {
        "msisdn": msisdn,
        "report": report,
        "report_source": report_source,
        "decision_locked": True,
    }


def build_client_report_context(msisdn: str, db: Session) -> dict[str, Any] | None:
    client = BadDebtsService(db).get_client(msisdn)
    if not client:
        return None

    profile = build_client_profile(client)
    explanations = build_explanations(client)
    decision = decide_next_action(client, explanations)
    deterministic_analysis = build_deterministic_client_analysis(client, profile, explanations, decision)
    contact_proposal = generate_message(client, decision)

    return {
        "decision_locked": True,
        "client": {
            "msisdn_masked": _mask_msisdn(msisdn),
            "cluster_name": client.get("cluster_name"),
            "state": client.get("state"),
            "risk_label": _safe_risk_label(client.get("risk_label")),
            "raw_risk_tier": decision.get("raw_risk_tier") or client.get("risk_tier"),
            "effective_tier": decision.get("effective_tier"),
            "final_risk_score": _round(client.get("final_risk_score")),
            "is_anomaly": bool(client.get("is_anomaly")),
            "anomaly_escalated": bool(decision.get("anomaly_escalated")),
            "total_outstanding_amount": _round(client.get("total_outstanding_amount")),
            "avg_reimburse_ratio": _round(client.get("avg_reimburse_ratio")),
            "debt_to_credit": _round(client.get("debt_to_credit")),
            "nb_sos": client.get("nb_sos"),
            "top_drivers": _safe_top_drivers(client.get("top_drivers")),
        },
        "decision": {
            "recommended_action": decision.get("recommended_action") or decision.get("action_type"),
            "recommended_action_label": decision.get("recommended_action_label"),
            "priority": decision.get("priority"),
            "priority_label": decision.get("priority_label"),
            "next_best_action": decision.get("next_best_action") or decision.get("recommendation"),
        },
        "contact_proposal": {
            "contact_type": contact_proposal.get("contact_type"),
            "title": contact_proposal.get("title"),
            "message_text": contact_proposal.get("message_text"),
            "safe_to_send": bool(contact_proposal.get("safe_to_send")),
            "internal_notice": contact_proposal.get("internal_notice"),
        },
        "explanations": {
            "business_rules": (explanations.get("business_rules") or [])[:5],
            "primary_factors": _safe_top_drivers(explanations.get("primary_factors")),
        },
        "deterministic_analysis": {
            "decision_reasoning": deterministic_analysis.get("decision_reasoning"),
            "key_risk_factors": deterministic_analysis.get("key_risk_factors"),
            "recommended_next_steps": deterministic_analysis.get("recommended_next_steps"),
            "internal_note": deterministic_analysis.get("internal_note"),
            "confidence_level": deterministic_analysis.get("confidence_level"),
        },
    }


def call_ollama_json(prompt: str, model_name: str | None = None, num_predict: int | None = None) -> dict[str, Any] | None:
    global _LAST_LOCAL_MODEL_ERROR, _LAST_LOCAL_MODEL_SECONDS
    _LAST_LOCAL_MODEL_ERROR = ""
    _LAST_LOCAL_MODEL_SECONDS = None
    base_url = str(settings.BAD_DEBTS_OLLAMA_BASE_URL or "").rstrip("/")
    if not base_url:
        _LAST_LOCAL_MODEL_ERROR = "base_url_missing"
        return None
    
    target_model = model_name or settings.BAD_DEBTS_OLLAMA_MODEL
    
    options: dict[str, Any] = {
        "temperature": float(settings.BAD_DEBTS_OLLAMA_TEMPERATURE),
        "num_predict": int(num_predict or settings.BAD_DEBTS_OLLAMA_NUM_PREDICT),
    }
    num_ctx = getattr(settings, "BAD_DEBTS_OLLAMA_NUM_CTX", None)
    if num_ctx:
        options["num_ctx"] = int(num_ctx)

    payload = {
        "model": target_model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": options,
    }
    keep_alive = str(getattr(settings, "BAD_DEBTS_OLLAMA_KEEP_ALIVE", "") or "").strip()
    if keep_alive:
        payload["keep_alive"] = keep_alive
    start = time.perf_counter()
    try:
        response = requests.post(
            f"{base_url}/api/generate",
            json=payload,
            timeout=int(settings.BAD_DEBTS_OLLAMA_TIMEOUT_SECONDS),
        )
        _LAST_LOCAL_MODEL_SECONDS = time.perf_counter() - start
        response.raise_for_status()
        data = response.json()
        raw = data.get("response")
        if isinstance(raw, dict):
            return raw
        if not raw:
            _LAST_LOCAL_MODEL_ERROR = "empty_response"
            return None
        parsed = _parse_local_model_json(raw)
        if isinstance(parsed, dict):
            return parsed
        _LAST_LOCAL_MODEL_ERROR = "json_not_object"
        return None
    except requests.Timeout:
        _LAST_LOCAL_MODEL_SECONDS = time.perf_counter() - start
        _LAST_LOCAL_MODEL_ERROR = "timeout"
        return None
    except json.JSONDecodeError:
        _LAST_LOCAL_MODEL_SECONDS = time.perf_counter() - start
        _LAST_LOCAL_MODEL_ERROR = "json_invalid"
        return None
    except RequestException:
        _LAST_LOCAL_MODEL_SECONDS = time.perf_counter() - start
        _LAST_LOCAL_MODEL_ERROR = "request_error"
        return None
    except (ValueError, TypeError):
        _LAST_LOCAL_MODEL_SECONDS = time.perf_counter() - start
        _LAST_LOCAL_MODEL_ERROR = "parse_error"
        return None


def _parse_local_model_json(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        return raw
    text = str(raw or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"\s*```$", "", text).strip()

    candidates = [text]
    first = text.find("{")
    last = text.rfind("}")
    if first >= 0 and last > first:
        candidates.append(text[first:last + 1])
    candidates.extend(re.sub(r",\s*([}\]])", r"\1", candidate) for candidate in list(candidates))

    decoder = json.JSONDecoder()
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            try:
                parsed, _ = decoder.raw_decode(candidate)
            except json.JSONDecodeError:
                continue
        if isinstance(parsed, dict):
            return parsed
    raise json.JSONDecodeError("invalid local model JSON", text, 0)


def validate_client_llm_report(report: dict[str, Any], context: dict[str, Any]) -> bool:
    if not isinstance(report, dict):
        return False
    if any(field not in report for field in REPORT_REQUIRED_FIELDS):
        return False

    text_limits = {
        "title": 120,
        "case_reading": 520,
        "signals_interpretation": 520,
        "operational_risk": 520,
        "argued_recommendation": 520,
        "manager_summary": 420,
    }
    for field, limit in text_limits.items():
        value = report.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            return False

    if not _valid_string_list(report.get("verification_points"), min_len=2, max_len=5):
        return False
    if report.get("confidence") not in {"élevée", "moyenne", "faible"}:
        return False
    sms_proposal = report.get("sms_proposal")
    action = str((context.get("decision") or {}).get("recommended_action") or "")
    if action == "sms_retention_offer":
        if not isinstance(sms_proposal, str) or not sms_proposal.strip():
            return False
    elif sms_proposal not in (None, ""):
        return False

    combined = json.dumps(report, ensure_ascii=False, default=str).lower()
    if any(term in combined for term in TECHNICAL_FORBIDDEN_TERMS):
        return False
    if any(term in combined for term in BUSINESS_FORBIDDEN_TERMS):
        return False
    if any(phrase in combined for phrase in _PHRASES_FORBIDDEN_GLOBAL):
        return False
    if _contains_complete_msisdn(combined):
        return False
    if not _generated_numbers_are_allowed(_client_report_narrative(report), _allowed_client_numbers(context)):
        return False
    narrative = _client_report_narrative(report).lower()
    if not _decision_is_coherent(narrative, context):
        return False
    if not _client_context_is_respected(narrative, context):
        return False
    return True


def fallback_client_report(context: dict[str, Any]) -> dict[str, Any]:
    client = context.get("client") or {}
    decision = context.get("decision") or {}
    contact = context.get("contact_proposal") or {}
    analysis = context.get("deterministic_analysis") or {}
    tier = _tier_label(client.get("effective_tier"))
    action = str(decision.get("recommended_action_label") or "Suivi routine")
    signals = list(analysis.get("key_risk_factors") or [])
    if not signals:
        signals = [f"Niveau de risque effectif {tier}", f"Action recommandée : {action}"]

    if client.get("effective_tier") == "high":
        case_reading = "Le cas présente un niveau d’exposition élevé qui nécessite une qualification humaine avant décision opérationnelle."
        signals_interpretation = "Les signaux disponibles convergent vers un suivi renforcé, sans transformer l’analyse en décision automatique."
        operational_risk = "Le risque opérationnel principal est de laisser un profil sensible sans qualification par l’équipe."
        verification_points = [
            "Confirmer la situation du client avant tout traitement.",
            "Vérifier les signaux qui expliquent la priorité élevée.",
            "S’assurer que le suivi reste professionnel et proportionné.",
        ]
        argued_recommendation = "L’appel prioritaire centre de relation client est justifié pour qualifier le cas et cadrer la suite métier."
        manager_summary = "Le dossier doit être priorisé par le centre de relation client, sans SMS automatique ni ton coercitif."
        confidence = "moyenne"
    elif client.get("effective_tier") == "medium":
        case_reading = "Le cas relève d’une surveillance préventive : le profil n’appelle pas d’urgence, mais mérite un contact léger."
        signals_interpretation = "Les signaux suggèrent une vigilance proportionnée plutôt qu’un traitement prioritaire."
        operational_risk = "Le risque opérationnel est de manquer un signal intermédiaire si aucun suivi n’est maintenu."
        verification_points = [
            "Vérifier que le message reste neutre et informatif.",
            "Confirmer que les signaux ne nécessitent pas d’escalade métier.",
        ]
        argued_recommendation = "Le SMS personnalisé est cohérent avec un risque moyen, car il maintient le lien sans promettre de solution commerciale."
        manager_summary = "Le suivi recommandé est préventif, mesuré et compatible avec un SMS neutre."
        confidence = "moyenne"
    else:
        case_reading = "Le cas reste stable et compatible avec un suivi routine."
        signals_interpretation = "Les signaux ne justifient pas d’action prioritaire à ce stade."
        operational_risk = "Le risque opérationnel reste limité tant que les indicateurs ne se dégradent pas."
        verification_points = [
            "Maintenir le suivi standard.",
            "Réexaminer le dossier uniquement si de nouveaux signaux apparaissent.",
        ]
        argued_recommendation = "Le suivi routine est cohérent avec un risque faible et évite toute dramatisation inutile."
        manager_summary = "Aucune action immédiate n’est requise ; le dossier peut rester dans le suivi courant."
        confidence = "moyenne"

    sms_proposal = None
    if decision.get("recommended_action") == "sms_retention_offer" and contact.get("message_text"):
        sms_proposal = str(contact.get("message_text"))

    return {
        "title": "Rapport métier client",
        "case_reading": case_reading,
        "signals_interpretation": signals_interpretation,
        "operational_risk": operational_risk,
        "verification_points": _limit_list(verification_points, 2, 5),
        "argued_recommendation": argued_recommendation,
        "sms_proposal": sms_proposal,
        "manager_summary": manager_summary,
        "confidence": confidence,
    }


def _client_report_prompt(context: dict[str, Any]) -> str:
    compact_context = json.dumps(context, ensure_ascii=False, default=str, separators=(",", ":"))
    return (
        "Rapport métier Bad Debts en français. Tu rédiges uniquement l'interprétation métier du cas client. "
        "Ne répète pas les KPIs, la recommandation principale ni la liste brute des facteurs. "
        "Python est source de vérité pour MSISDN, segment, score, risque, anomalie, dette, remboursement, action, priorité, facteurs et proposition de contact. "
        "Décision verrouillée: ne change pas risque/action/priorité/chiffres. N'invente aucun chiffre ni fait client. "
        "Ne dis jamais qu'un SMS a été envoyé ou qu'un conseiller a appelé. Ne promets aucune solution. "
        "Si l'action n'est pas sms_retention_offer, sms_proposal doit être null. Pour risque élevé ou faible, aucun SMS. "
        "Pour risque moyen avec SMS personnalisé, sms_proposal doit être court, neutre et sans offre commerciale. "
        "Interdits: LangGraph, LLM, OpenAI, Ollama, GPT, FastAPI, PostgreSQL, API, JSON, backend, frontend, prompt, "
        "token, n8n, payload, run_id, action_id, agent_run_id, fraude, frauduleux, blacklist, menace, harcèlement, "
        "remise, réduction, bonus, cadeau, offre commerciale, plan d'apurement, offre de restructuration, sanction, contentieux, poursuite, fallback. "
        "Réponds seulement avec un objet JSON contenant: case_reading, signals_interpretation, operational_risk, "
        "verification_points, argued_recommendation, sms_proposal, manager_summary, confidence. "
        "verification_points contient 2 à 5 textes concrets. confidence: élevée, moyenne ou faible. "
        f"Contexte:{compact_context}"
    )


def _client_report_enabled() -> bool:
    return (
        bool(settings.BAD_DEBTS_ENABLE_CLIENT_REPORT)
        and bool(settings.BAD_DEBTS_OLLAMA_ENABLED)
        and str(settings.BAD_DEBTS_LLM_PROVIDER or "").lower() == "ollama"
    )


def _normalize_report(report: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    base = fallback_client_report(context) if context else None
    if base is None:
        base = {
            "title": "Rapport métier client",
            "case_reading": "Lecture métier disponible.",
            "signals_interpretation": "Les signaux disponibles doivent être interprétés dans le contexte métier.",
            "operational_risk": "Le risque opérationnel dépend du niveau de suivi requis.",
            "verification_points": ["Vérifier le dossier client.", "Confirmer les signaux avant décision."],
            "argued_recommendation": "La recommandation suit les règles métier définies.",
            "sms_proposal": None,
            "manager_summary": "Synthèse disponible pour responsable métier.",
        }
    action = str(((context or {}).get("decision") or {}).get("recommended_action") or "")
    sms_proposal = str(report.get("sms_proposal") or "").strip() or base.get("sms_proposal")
    if action != "sms_retention_offer":
        sms_proposal = None
    return {
        **base,
        "case_reading": str(report.get("case_reading") or base.get("case_reading") or "").strip(),
        "signals_interpretation": str(report.get("signals_interpretation") or base.get("signals_interpretation") or "").strip(),
        "operational_risk": str(report.get("operational_risk") or base.get("operational_risk") or "").strip(),
        "verification_points": _pad_report_list(
            _normalize_text_list(report.get("verification_points")),
            list(base.get("verification_points") or []),
            5,
        ),
        "argued_recommendation": str(report.get("argued_recommendation") or base.get("argued_recommendation") or "").strip(),
        "sms_proposal": sms_proposal,
        "manager_summary": str(report.get("manager_summary") or base.get("manager_summary") or "").strip(),
        "confidence": str(report.get("confidence") or "").strip(),
    }


def _normalize_text_list(value: Any, *, signal_mode: bool = False) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    elif value:
        raw_items = [value]
    else:
        raw_items = []
    result = []
    for item in raw_items:
        text = _signal_to_text(item) if signal_mode else str(item or "").strip()
        if text:
            result.append(text)
    return result


def _pad_report_list(values: list[str], defaults: list[str], max_len: int) -> list[str]:
    result = [item for item in values if item][:max_len]
    for item in defaults:
        if len(result) >= 2:
            break
        if item not in result:
            result.append(item)
    return result[:max_len]


def _decision_is_coherent(combined: str, context: dict[str, Any]) -> bool:
    decision = context.get("decision") or {}
    action = str(decision.get("recommended_action") or "")
    priority = str(decision.get("priority_label") or "").lower()
    if action == "monitor_only" and any(term in combined for term in ("appel prioritaire", "très urgent", "tres urgent")):
        return False
    if action == "call_center_priority" and "aucune action" in combined:
        return False
    if action == "sms_retention_offer" and "appel prioritaire" in combined:
        return False
    if priority == "normal" and any(term in combined for term in ("très urgent", "tres urgent", "urgent prioritaire")):
        return False
    if priority == "très urgent" and "priorité normale" in combined:
        return False
    return True


def _client_context_is_respected(combined: str, context: dict[str, Any]) -> bool:
    client = context.get("client") or {}
    decision = context.get("decision") or {}
    action = str(decision.get("recommended_action") or "")
    tier = str(client.get("effective_tier") or "")
    if action == "call_center_priority" and any(term in combined for term in ("sms envoyé", "sms direct", "envoyer un sms")):
        return False
    if action == "sms_retention_offer" and any(term in combined for term in ("appel prioritaire", "script d'appel")):
        return False
    if action == "monitor_only" and any(term in combined for term in ("urgence", "critique", "prioritaire")):
        return False
    if tier == "low" and any(term in combined for term in ("urgence", "critique", "crise", "très urgent", "tres urgent")):
        return False
    if tier == "medium" and any(term in combined for term in ("crise", "critique")):
        return False
    if not bool(client.get("is_anomaly")) and "anomal" in combined:
        return False
    if bool(client.get("is_anomaly")) and any(term in combined for term in ("preuve", "certain", "confirmé")):
        return False
    debt = client.get("total_outstanding_amount")
    try:
        debt_value = float(debt) if debt is not None else None
    except (TypeError, ValueError):
        debt_value = None
    if debt_value is not None and debt_value == 0 and any(term in combined for term in ("dette active", "encours actif", "impayé actif", "impaye actif", "montant à recouvrer")):
        return False
    reimb = client.get("avg_reimburse_ratio")
    try:
        reimb_value = float(reimb) if reimb is not None else None
    except (TypeError, ValueError):
        reimb_value = None
    reimb_percent = reimb_value * 100 if reimb_value is not None and reimb_value <= 1 else reimb_value
    if reimb_percent is not None and reimb_percent >= 95 and any(term in combined for term in ("remboursement faible", "remboursement dégradé", "moins régulier", "baisse de remboursement")):
        return False
    if any(term in combined for term in ("a été envoyé", "sms envoyé", "appel effectué", "conseiller a appelé")):
        return False
    return True


def _valid_string_list(value: Any, *, min_len: int, max_len: int) -> bool:
    if not isinstance(value, list) or not (min_len <= len(value) <= max_len):
        return False
    return all(isinstance(item, str) and item.strip() and len(item) <= 220 for item in value)


def _contains_complete_msisdn(text: str) -> bool:
    return bool(re.search(r"\b216\d{5,9}\b", str(text or ""))) or bool(re.search(r"\b\d{8,12}\b", str(text or "")))


def _client_report_narrative(report: dict[str, Any]) -> str:
    return json.dumps(
        {
            "title": report.get("title"),
            "case_reading": report.get("case_reading"),
            "signals_interpretation": report.get("signals_interpretation"),
            "operational_risk": report.get("operational_risk"),
            "verification_points": report.get("verification_points"),
            "argued_recommendation": report.get("argued_recommendation"),
            "sms_proposal": report.get("sms_proposal"),
            "manager_summary": report.get("manager_summary"),
        },
        ensure_ascii=False,
        default=str,
    )


def _global_report_number_narrative(report: dict[str, Any]) -> str:
    decision_focus = []
    for item in report.get("decision_support") or []:
        if isinstance(item, dict):
            decision_focus.append(item.get("recommended_focus"))
    return json.dumps(
        {
            "executive_summary": report.get("executive_summary"),
            "risk_reading": report.get("risk_reading"),
            "business_rationale": report.get("business_rationale"),
            "main_findings": report.get("main_findings"),
            "business_recommendations": report.get("business_recommendations"),
            "decision_support_focus": decision_focus,
        },
        ensure_ascii=False,
        default=str,
    )


def _allowed_client_numbers(context: dict[str, Any]) -> set[str]:
    client = context.get("client") or {}
    decision = context.get("decision") or {}
    allowed: set[str] = {"1", "2", "3", "4"}
    for key in (
        "final_risk_score",
        "total_outstanding_amount",
        "avg_reimburse_ratio",
        "debt_to_credit",
        "nb_sos",
    ):
        _add_allowed_number(allowed, client.get(key))
    _add_allowed_number(allowed, decision.get("priority"))
    return allowed


def _allowed_global_numbers(kpis: dict[str, Any]) -> set[str]:
    allowed: set[str] = {"1", "2", "3", "4"}
    total = int(kpis.get("total_clients") or 0)
    for key in ("total_clients", "clients_high", "clients_medium", "clients_low", "clients_with_anomaly"):
        _add_allowed_number(allowed, kpis.get(key))
    for key in ("average_risk_score", "average_debt", "average_reimbursement_ratio"):
        _add_allowed_number(allowed, kpis.get(key))

    if total:
        for key in ("clients_high", "clients_medium", "clients_low", "clients_with_anomaly"):
            _add_allowed_number(allowed, round(int(kpis.get(key) or 0) / total * 100))
    reimb = kpis.get("average_reimbursement_ratio")
    if reimb is not None:
        _add_allowed_number(allowed, round(float(reimb) * 100))
    debt = kpis.get("average_debt")
    if debt is not None:
        _add_allowed_number(allowed, round(float(debt)))
    score = kpis.get("average_risk_score")
    if score is not None:
        _add_allowed_number(allowed, round(float(score), 3))
    return allowed


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


def _generated_numbers_are_allowed(text: str, allowed: set[str]) -> bool:
    scrubbed = re.sub(r"priorit[ée]\s*[0-9]+", "", str(text or ""), flags=re.IGNORECASE)
    scrubbed = re.sub(r"\b[0-9]+\s*(:er|e|ème|eme)\b", "", scrubbed, flags=re.IGNORECASE)
    for raw in re.findall(r"\d+(?:[\s\u202f]\d{3})*(?:[.,]\d+)?|\d+", scrubbed):
        normalized = raw.replace("\u202f", "").replace(" ", "").replace(",", ".")
        if normalized.startswith("216") and len(normalized) >= 8:
            return False
        if normalized not in allowed:
            return False
    return True


def _safe_top_drivers(value: Any, limit: int = 5) -> list[Any]:
    raw = value if isinstance(value, list) else [value] if value else []
    safe = []
    for item in raw[:limit]:
        if isinstance(item, dict):
            feature = item.get("feature") or item.get("name")
            safe.append(_driver_label(feature))
        else:
            safe.append(_driver_label(item))
    return safe


def _public_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    blocked = {"run_id", "action_id", "agent_run_id", "payload", "llm_model", "llm_error"}
    return {key: item for key, item in value.items() if key not in blocked}


def _safe_profile(value: dict[str, Any]) -> dict[str, Any]:
    profile = _public_dict(value)
    profile.pop("msisdn", None)
    profile.pop("summary", None)
    return profile


def _safe_risk_label(value: Any) -> str | None:
    label = str(value or "").strip()
    if not label:
        return None
    if "blacklist" in label.lower():
        return "Segment sensible"
    return label


def _signal_to_text(value: Any) -> str:
    if isinstance(value, dict):
        return _driver_label(value.get("feature") or value.get("name"))
    return _driver_label(value)


def _driver_label(value: Any) -> str:
    labels = {
        "AVG_CREDIT_AMOUNT": "Montant moyen crédité",
        "avg_credit_amount": "Montant moyen crédité",
        "never_repaid": "Aucun remboursement détecté",
        "reimburse_ratio": "Ratio de remboursement",
        "TOTAL_OUTSTANDING_AMOUNT": "Encours restant",
        "total_outstanding_amount": "Encours restant",
        "credit_intensity": "Fréquence d'utilisation SOS",
        "full_repayer": "Historique de remboursement complet",
        "debt_to_credit": "Dette rapportée au crédit",
        "NB_SOS": "Nombre d'usages SOS",
    }
    key = str(value or "").strip()
    return labels.get(key, key if key else "")


def _mask_msisdn(value: Any) -> str:
    text = str(value or "")
    if len(text) <= 4:
        return "****"
    return f"{text[:3]}****{text[-2:]}"


def _round(value: Any, digits: int = 3) -> float | None:
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _tier_label(value: Any) -> str:
    tier = str(value or "").lower()
    if tier == "high":
        return "élevé"
    if tier == "medium":
        return "moyen"
    return "faible"


def _limit_list(values: list[Any], min_len: int, max_len: int) -> list[str]:
    result = [str(value).strip() for value in values if str(value).strip()][:max_len]
    while len(result) < min_len:
        result.append("Signal ML disponible")
    return result


# ---------------------------------------------------------------------------
# Global report
# ---------------------------------------------------------------------------

_GLOBAL_REPORT_REQUIRED_FIELDS = (
    "report_title",
    "executive_summary",
    "risk_reading",
    "business_rationale",
    "decision_support",
    "main_findings",
    "business_recommendations",
)

_GLOBAL_TECHNICAL_FORBIDDEN = TECHNICAL_FORBIDDEN_TERMS
_DECISION_SUPPORT_RAW_FORBIDDEN = (
    "risk_tier",
    "effective_tier",
    "cluster_name",
    "recommended_action",
    "sms_retention_offer",
    "call_center_priority",
    "monitor_only",
)

_GLOBAL_BUSINESS_FORBIDDEN = BUSINESS_FORBIDDEN_TERMS

_PHRASES_FORBIDDEN_GLOBAL = (
    "ne remplace pas",
    "utiliser uniquement",
    "réexaminer le périmètre",
    "vérifier la cohérence",
    "aide à la décision uniquement",
    "100 % du portefeuille",
    "le portefeuille est composé",
    "sur l'ensemble du portefeuille",
    "tendance globale du portefeuille",
    "au sein du portefeuille",
    "le portefeuille représente",
)

_ACTION_LABELS_FR = {
    "call_center_priority": "Appel prioritaire centre de relation client",
    "sms_retention_offer": "SMS personnalisé",
    "monitor_only": "Suivi routine",
}

_SEGMENT_LABELS_FR = {
    "DISCONNECTED": "Déconnecté",
    "SUSPENDED": "Suspendu",
    "ON-HOLD": "En attente",
    "Bon-payeur": "Bon payeur",
    "Standard": "Standard",
}

_TIER_LABELS_FR = {
    "high": "élevé",
    "medium": "moyen",
    "low": "faible",
}

_EMPTY_REPORT_SUMMARY = (
    "Aucun client ne correspond aux filtres sélectionnés. "
    "Il est recommandé d'élargir le périmètre d'analyse ou de réinitialiser les filtres afin d'obtenir une population exploitable."
)


def generate_global_llm_report(
    service: BadDebtsService,
    filters: dict[str, Any],
) -> dict[str, Any]:
    risk_tier = filters.get("risk_tier")
    cluster_name = filters.get("cluster_name")
    is_anomaly = filters.get("is_anomaly")
    recommended_action = filters.get("recommended_action")
    search = filters.get("search")

    kpis = service.compute_global_kpis(
        risk_tier=risk_tier,
        cluster_name=cluster_name,
        is_anomaly=is_anomaly,
        recommended_action=recommended_action,
        search=search,
    )

    active_filters = {k: v for k, v in filters.items() if v is not None}
    scope = "filtered" if active_filters else "global"
    if (
        active_filters.get("cluster_name") == "Bon-payeur"
        and active_filters.get("risk_tier") == "medium"
        and "is_anomaly" not in active_filters
        and int(kpis.get("total_clients") or 0) > 0
        and int(kpis.get("clients_with_anomaly") or 0) == int(kpis.get("total_clients") or 0)
    ):
        active_filters["is_anomaly"] = True
        filter_labels = _filter_labels_for_prompt(active_filters)
        if filter_labels:
            kpis["filter_summary"] = "Filtres actifs : " + ", ".join(filter_labels)
    
    # Python builds the deterministic business context before LLM call
    decision_context = build_global_decision_context(kpis, active_filters)

    report_source = "deterministic_fallback"
    report = _fallback_global_report_final(kpis, active_filters, decision_context)
    fallback_reason = "local_model_disabled"
    model_seconds = None
    primary_model = str(settings.BAD_DEBTS_OLLAMA_MODEL or "").strip()
    backup_model = str(settings.BAD_DEBTS_OLLAMA_BACKUP_MODEL or "").strip()
    used_model = primary_model
    backup_used = False
    primary_error = ""
    backup_error = ""

    if _global_report_enabled() and int(kpis.get("total_clients") or 0) > 0:
        prompt = _global_report_prompt(kpis, active_filters, decision_context)

        generated = call_ollama_json(prompt, model_name=primary_model)
        model_seconds = _LAST_LOCAL_MODEL_SECONDS
        primary_error = _LAST_LOCAL_MODEL_ERROR or ""
        fallback_reason = primary_error or "unknown"
        used_model = primary_model

        normalized = _sanitize_fast_ai_narrative(_normalize_global_report(generated)) if generated else None
        validation_errors = validate_fast_ai_narrative(normalized, kpis, active_filters, decision_context) if normalized else ["generation_failed"]
        if validation_errors:
            primary_error = primary_error or "validation_failed: " + "; ".join(validation_errors[:4])

        if validation_errors and backup_model and backup_model != primary_model:
            generated = call_ollama_json(prompt, model_name=backup_model)
            model_seconds = (model_seconds or 0) + (_LAST_LOCAL_MODEL_SECONDS or 0)
            used_model = backup_model
            backup_used = True
            backup_error = _LAST_LOCAL_MODEL_ERROR or ""
            
            normalized = _sanitize_fast_ai_narrative(_normalize_global_report(generated)) if generated else None
            validation_errors = validate_fast_ai_narrative(normalized, kpis, active_filters, decision_context) if normalized else ["backup_generation_failed"]
            if validation_errors:
                backup_error = backup_error or "validation_failed: " + "; ".join(validation_errors[:4])

        if not validation_errors and normalized:
            report = _repair_global_report_sections(normalized, kpis, active_filters, decision_context)
            report_source = "local_llm"
            fallback_reason = ""
        else:
            fallback_reason = "validation_failed: " + "; ".join(validation_errors[:4])

    return {
        "scope": scope,
        "filters": active_filters,
        "kpis": kpis,
        "report": report,
        "report_source": report_source,
        "report_generation": {
            "model_provider": settings.BAD_DEBTS_LLM_PROVIDER,
            "model": used_model,
            "primary_model": primary_model,
            "backup_model": backup_model or None,
            "backup_used": backup_used,
            "model_seconds": model_seconds,
            "fallback_reason": fallback_reason,
            "primary_error": primary_error,
            "backup_error": backup_error,
        },
        "decision_locked": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _global_report_enabled() -> bool:
    return (
        bool(settings.BAD_DEBTS_OLLAMA_ENABLED)
        and bool(settings.BAD_DEBTS_OLLAMA_BASE_URL)
        and str(settings.BAD_DEBTS_LLM_PROVIDER or "").lower() == "ollama"
    )


def _contains_forbidden_term(text: str, term: str) -> bool:
    if not term:
        return False
    if term.isascii() and term.isalnum() and len(term) <= 4:
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text))
    return term in text


def _fmt(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _global_key_kpis(kpis: dict[str, Any]) -> list[dict[str, str]]:
    total = int(kpis.get("total_clients") or 0)
    high = int(kpis.get("clients_high") or 0)
    medium = int(kpis.get("clients_medium") or 0)
    low = int(kpis.get("clients_low") or 0)
    anomaly = int(kpis.get("clients_with_anomaly") or 0)
    avg_score = kpis.get("average_risk_score")
    avg_debt = kpis.get("average_debt")
    avg_reimb = kpis.get("average_reimbursement_ratio")
    high_pct = round(high / total * 100) if total else 0
    medium_pct = round(medium / total * 100) if total else 0
    low_pct = round(low / total * 100) if total else 0
    score_val = float(avg_score) if avg_score is not None else None
    debt_val = float(avg_debt) if avg_debt is not None else None
    reimb_pct = round(float(avg_reimb) * 100) if avg_reimb is not None else None
    return [
        {"label": "Clients scorés", "value": _fmt(total), "comment": kpis.get("filter_summary") or "Tous les clients du portefeuille"},
        {"label": "Clients à risque élevé", "value": _fmt(high), "comment": f"{high_pct} % du périmètre"},
        {"label": "Clients à risque moyen", "value": _fmt(medium), "comment": f"{medium_pct} % du périmètre"},
        {"label": "Clients à risque faible", "value": _fmt(low), "comment": f"{low_pct} % du périmètre"},
        {"label": "Anomalies détectées", "value": _fmt(anomaly), "comment": ""},
        {"label": "Score de risque moyen", "value": f"{round(score_val, 3)}" if score_val is not None else "-", "comment": "Score agrégé"},
        {"label": "Dette moyenne", "value": f"{_fmt(round(debt_val))} TND" if debt_val is not None else "-", "comment": "Montant moyen par client"},
        {"label": "Taux de remboursement moyen", "value": f"{reimb_pct} %" if reimb_pct is not None else "-", "comment": "Ratio moyen"},
    ]


def _global_report_title(active_filters: dict[str, Any], total: int) -> str:
    if total == 0:
        return "Rapport de pilotage Bad Debts — Aucun résultat"
    if not active_filters:
        return "Rapport de pilotage Bad Debts — Portefeuille global"

    risk = active_filters.get("risk_tier")
    segment = active_filters.get("cluster_name")
    anomaly = active_filters.get("is_anomaly")
    action = active_filters.get("recommended_action")
    search = active_filters.get("search")

    if search:
        return "Rapport de pilotage Bad Debts — Résultat de recherche client"

    seg_label = _SEGMENT_LABELS_FR.get(str(segment), str(segment)) if segment else ""
    risk_label = _TIER_LABELS_FR.get(str(risk), str(risk)) if risk else ""
    action_label = _ACTION_LABELS_FR.get(str(action), str(action)) if action else ""
    anomaly_label = "avec anomalie" if anomaly is True else "sans anomalie" if anomaly is False else ""
    if segment and risk and anomaly is not None:
        return f"Rapport de pilotage Bad Debts — Segment {seg_label} à risque {risk_label} {anomaly_label}"
    if segment and risk:
        return f"Rapport de pilotage Bad Debts — Segment {seg_label} à risque {risk_label}"
    if segment and anomaly is not None:
        return f"Rapport de pilotage Bad Debts — Segment {seg_label} {anomaly_label}"
    if risk and anomaly is not None:
        return f"Rapport de pilotage Bad Debts — Risque {risk_label} {anomaly_label}"
    if action and anomaly is not None:
        return f"Rapport de pilotage Bad Debts — {action_label} {anomaly_label}"
    if segment:
        return f"Rapport de pilotage Bad Debts — Segment {seg_label}"
    if risk:
        return f"Rapport de pilotage Bad Debts — Clients à risque {risk_label}"
    if anomaly is True:
        return "Rapport de pilotage Bad Debts — Clients avec anomalie"
    if anomaly is False:
        return "Rapport de pilotage Bad Debts — Clients sans anomalie"
    if action:
        if action == "call_center_priority":
            return "Rapport de pilotage Bad Debts — Appel prioritaire"
        return f"Rapport de pilotage Bad Debts — {action_label}"
    return "Rapport de pilotage Bad Debts — Périmètre filtré"


def _filter_labels_for_prompt(active_filters: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    risk = active_filters.get("risk_tier")
    segment = active_filters.get("cluster_name")
    anomaly = active_filters.get("is_anomaly")
    action = active_filters.get("recommended_action")
    search = active_filters.get("search")
    if risk:
        labels.append(f"Risque : {_TIER_LABELS_FR.get(str(risk), str(risk)).capitalize()}")
    if segment:
        labels.append(f"Segment : {_SEGMENT_LABELS_FR.get(str(segment), str(segment))}")
    if anomaly is True:
        labels.append("Anomalie : Oui")
    elif anomaly is False:
        labels.append("Anomalie : Non")
    if action:
        labels.append(f"Action : {_ACTION_LABELS_FR.get(str(action), str(action))}")
    if search:
        labels.append("Recherche client : active")
    return labels


def _fallback_global_report(kpis: dict[str, Any], active_filters: dict[str, Any]) -> dict[str, Any]:  # noqa: C901
    """Generate a deterministic report strictly coherent with KPI values."""
    # Base values
    total = int(kpis.get("total_clients") or 0)
    high = int(kpis.get("clients_high") or 0)
    medium = int(kpis.get("clients_medium") or 0)
    low = int(kpis.get("clients_low") or 0)
    anomaly = int(kpis.get("clients_with_anomaly") or 0)
    avg_score = kpis.get("average_risk_score")
    avg_debt = kpis.get("average_debt")
    avg_reimb = kpis.get("average_reimbursement_ratio")
    dominant_seg_raw = kpis.get("dominant_segment") or ""
    dominant_seg = _SEGMENT_LABELS_FR.get(dominant_seg_raw, dominant_seg_raw) or "Non defini"
    dominant_action = kpis.get("dominant_recommended_action") or "monitor_only"
    filter_summary = kpis.get("filter_summary") or "Tous les clients du portefeuille"

    is_global = not active_filters
    filter_rt = active_filters.get("risk_tier")
    filter_seg = active_filters.get("cluster_name")
    filter_anom = active_filters.get("is_anomaly")
    filter_action = active_filters.get("recommended_action")

    # Early return: empty perimeter
    if total == 0:
        return {
            "report_title": "Rapport de pilotage Bad Debts — Aucun résultat",
            "executive_summary": (
                "Aucun client ne correspond aux critères sélectionnés. "
                "Les filtres appliqués ne retournent aucune donnée disponible."
            ),
            "risk_reading": "Aucune donnée disponible pour ce périmètre.",
            "key_kpis": [],
            "decision_support": [
                {
                    "priority": "Information",
                    "target": "Périmètre vide",
                    "business_goal": "Réviser les critères",
                    "recommended_focus": "Modifier les filtres pour obtenir un périmètre de clients à analyser.",
                }
            ],
            "main_findings": ["Aucun client ne correspond aux critères sélectionnés."],
            "business_recommendations": ["Modifier les filtres pour obtenir un périmètre de clients à analyser."],
            "decision_limits": "",
            "internal_note": "",
        }

    # Computed percentages
    high_pct = round(high / total * 100) if total else 0
    medium_pct = round(medium / total * 100) if total else 0
    low_pct = round(low / total * 100) if total else 0
    action_label_str = _ACTION_LABELS_FR.get(dominant_action, "Suivi routine")
    filter_action_label = _ACTION_LABELS_FR.get(str(filter_action or ""), "")

    score_val = float(avg_score) if avg_score is not None else None
    score_str = f"{round(score_val, 3)}" if score_val is not None else "non disponible"
    debt_str = f"{_fmt(round(float(avg_debt)))} TND" if avg_debt is not None else "non disponible"
    reimb_pct = round(float(avg_reimb) * 100) if avg_reimb is not None else None
    reimb_str = f"{reimb_pct} %" if reimb_pct is not None else "non disponible"

    # KPI reality flags — strictly override filter assumptions
    has_high = high > 0
    has_medium = medium > 0
    has_anomaly = anomaly > 0
    is_good_payer = reimb_pct is not None and reimb_pct >= 95
    is_low_reimb = reimb_pct is not None and reimb_pct < 60
    zero_debt = float(avg_debt or 0) == 0
    all_low = low == total and not has_high and not has_medium
    is_stable = all_low or (score_val is not None and score_val < 0.20)
    is_very_stable = all_low and not has_anomaly and is_good_payer and zero_debt
    seg_label = _SEGMENT_LABELS_FR.get(filter_seg, filter_seg) if filter_seg else ""

    # KPI cards
    key_kpis = [
        {"label": "Clients scorés", "value": _fmt(total), "comment": filter_summary},
        {"label": "Clients à risque élevé", "value": _fmt(high), "comment": f"{high_pct} % du périmètre"},
        {"label": "Clients à risque moyen", "value": _fmt(medium), "comment": f"{medium_pct} % du périmètre"},
        {"label": "Clients à risque faible", "value": _fmt(low), "comment": f"{low_pct} % du périmètre"},
        {"label": "Anomalies détectées", "value": _fmt(anomaly), "comment": ""},
        {"label": "Score de risque moyen", "value": score_str, "comment": "Indice ML agrégé"},
        {"label": "Dette moyenne", "value": debt_str, "comment": "Encours moyen par client"},
        {"label": "Taux de remboursement moyen", "value": reimb_str, "comment": "Ratio moyen de remboursement"},
    ]

    # Score / reimb interpretation (KPI-driven)
    if score_val is not None:
        if score_val >= 0.50:
            score_interp = "traduit un niveau de vigilance à maintenir, avec des profils nécessitant une attention ciblée"
        elif score_val >= 0.20:
            score_interp = "indique un risque global modéré, orienté vers une surveillance ciblée"
        else:
            score_interp = "reflète un périmètre globalement maîtrisé"
    else:
        score_interp = "est à analyser au niveau des profils individuels"

    if reimb_pct is not None:
        if reimb_pct >= 95:
            reimb_interp = "le taux de remboursement est très satisfaisant"
        elif reimb_pct >= 75:
            reimb_interp = "le comportement de remboursement est globalement satisfaisant"
        elif reimb_pct >= 55:
            reimb_interp = "des difficultés de remboursement partielles méritent une attention ciblée"
        else:
            reimb_interp = "le taux de remboursement signale des difficultés nécessitant un suivi renforcé"
    else:
        reimb_interp = "le comportement de remboursement doit être examiné profil par profil"

    # ── TITLE ──────────────────────────────────────────────────────────────
    if is_global:
        title = "Rapport de pilotage Bad Debts — Portefeuille global"
    elif filter_rt == "high":
        title = "Rapport de pilotage Bad Debts — Clients à risque élevé"
    elif filter_rt == "medium":
        title = "Rapport de pilotage Bad Debts — Clients à risque moyen"
    elif filter_rt == "low":
        title = "Rapport de pilotage Bad Debts — Clients à risque faible"
    elif filter_seg and filter_anom is True:
        title = f"Rapport de pilotage Bad Debts — {seg_label} avec anomalie"
    elif filter_seg and filter_anom is False:
        title = f"Rapport de pilotage Bad Debts — {seg_label} sans anomalie"
    elif filter_seg:
        title = f"Rapport de pilotage Bad Debts — Segment {seg_label}"
    elif filter_anom is True:
        title = "Rapport de pilotage Bad Debts — Clients avec anomalie"
    elif filter_anom is False:
        title = "Rapport de pilotage Bad Debts — Clients sans anomalie"
    elif filter_action:
        title = f"Rapport de pilotage Bad Debts — Action : {filter_action_label or filter_action}"
    else:
        title = "Rapport de pilotage Bad Debts — Périmètre filtré"

    # ── EXECUTIVE SUMMARY ──────────────────────────────────────────────────
    if is_global:
        if has_high:
            summary = (
                f"Le portefeuille présente une structure globalement maîtrisée, "
                f"avec {low_pct} % des clients en risque faible. "
                "La zone d'attention principale concerne les profils à risque élevé "
                "et les anomalies détectées, qui doivent être priorisés dans le pilotage métier. "
                f"Le segment dominant en volume est {dominant_seg}, mais l'analyse doit surtout se concentrer "
                "sur les segments où le score moyen est le plus élevé."
            )
        else:
            summary = (
                f"Le portefeuille présente une structure stable, "
                f"avec {low_pct} % des clients en risque faible et aucun client à risque élevé. "
                f"Le segment dominant en volume est {dominant_seg}. "
                "L'enjeu principal est le maintien d'un suivi standard et la surveillance préventive des profils à risque moyen."
            )
    elif filter_rt == "high":
        has_ano_reimb = has_anomaly and not is_good_payer
        summary = (
            "Ce périmètre concentre les profils à risque effectif élevé, "
            "qui constituent la cible prioritaire de toute action de pilotage. "
            + (
                "La combinaison entre le score de risque, les anomalies détectées "
                "et le taux de remboursement permet d'identifier les cas nécessitant un traitement immédiat. "
                if has_ano_reimb
                else "Le score de risque et le segment d'appartenance permettent d'affiner la priorisation. "
            )
            + f"L'action recommandée dominante sur ce périmètre est « {action_label_str} »."
        )
    elif filter_rt == "medium":
        if filter_anom is True:
            summary = (
                "Ce périmètre regroupe des clients à risque moyen avec anomalie détectée. "
                "Il ne s'agit pas d'une situation critique, mais d'un groupe à surveiller pour prévenir une éventuelle dégradation. "
                "L'objectif est de maintenir un suivi léger par SMS tout en surveillant l'évolution du score et du comportement de remboursement."
            )
        else:
            summary = (
                "Ce périmètre regroupe les profils à risque moyen, "
                "qui représentent une zone de transition entre stabilité et exposition au risque. "
                "Un suivi renforcé permet d'anticiper une éventuelle montée en risque avant qu'elle ne devienne prioritaire. "
                f"L'action recommandée dominante est « {action_label_str} »."
            )
    elif filter_rt == "low":
        summary = (
            "Ce périmètre regroupe les clients à risque faible, "
            "qui constituent la base stable du portefeuille. "
            + (
                "Le taux de remboursement satisfaisant confirme la maîtrise globale de ce périmètre. "
                if is_good_payer
                else "Le suivi standard de ce périmètre constitue une surveillance préventive de base. "
            )
            + "Ce segment peut servir de référence comparative pour évaluer les segments plus exposés."
        )
    elif filter_seg and filter_anom is True:
        if is_very_stable:
            summary = (
                f"Ce rapport porte sur les clients du segment {seg_label} présentant une anomalie. "
                "Malgré un profil d'ensemble stable — risque faible, remboursement satisfaisant et encours nul — "
                "les anomalies détectées constituent un signal atypique méritant une vérification contextuelle. "
                f"L'action recommandée dominante est « {action_label_str} »."
            )
        elif is_good_payer and not has_high:
            summary = (
                f"Ce rapport porte sur les clients du segment {seg_label} présentant une anomalie détectée. "
                "Malgré un taux de remboursement satisfaisant, la présence d'anomalies constitue un signal atypique "
                "qui mérite une analyse contextuelle. "
                f"L'action recommandée dominante est « {action_label_str} »."
            )
        else:
            summary = (
                f"Ce rapport porte sur les clients du segment {seg_label} présentant une anomalie détectée. "
                "Le croisement du signal d'anomalie avec le niveau de risque et le comportement de remboursement "
                "constitue le principal levier de priorisation des actions de suivi. "
                f"L'action recommandée dominante est « {action_label_str} »."
            )
    elif filter_seg and filter_anom is False:
        summary = (
            f"Ce rapport porte sur les clients du segment {seg_label} sans anomalie détectée. "
            + (
                f"Le périmètre présente {high_pct} % de clients à risque élevé, nécessitant une attention ciblée. "
                if has_high
                else "Le périmètre est globalement stable, sans signal atypique détecté. "
            )
            + f"L'action recommandée dominante est « {action_label_str} »."
        )
    elif filter_seg:
        if is_very_stable:
            summary = (
                f"Ce rapport porte sur le segment {seg_label}. "
                "Les indicateurs confirment un périmètre stable, sans anomalie détectée et avec un remboursement satisfaisant. "
                "Ce segment constitue une base de référence utile pour comparer les segments plus exposés. "
                f"L'action dominante est « {action_label_str} »."
            )
        else:
            summary = (
                f"Ce rapport porte sur le segment {seg_label}. "
                "L'analyse des indicateurs disponibles permet d'orienter le pilotage "
                "vers les profils les plus sensibles de ce segment. "
                f"L'action recommandée dominante est « {action_label_str} »."
            )
    elif filter_anom is True:
        if is_good_payer and not has_high:
            summary = (
                "Ce périmètre regroupe les clients présentant une anomalie détectée. "
                "Le taux de remboursement satisfaisant rend ces anomalies atypiques "
                "et invite à une vérification contextuelle. "
                f"L'action recommandée dominante est « {action_label_str} »."
            )
        elif has_high:
            summary = (
                "Ce périmètre regroupe les clients présentant une anomalie détectée. "
                "La combinaison anomalie et risque élevé constitue le signal de priorisation principal. "
                f"L'action recommandée dominante est « {action_label_str} »."
            )
        else:
            summary = (
                "Ce périmètre regroupe les clients présentant une anomalie détectée. "
                "L'anomalie constitue un signal de priorisation à croiser avec le niveau de risque "
                "et le comportement de remboursement pour orienter les actions de suivi. "
                f"L'action recommandée dominante est « {action_label_str} »."
            )
    elif filter_anom is False:
        summary = (
            "Ce périmètre regroupe les clients sans anomalie détectée. "
            + (
                f"Il présente {high_pct} % de clients à risque élevé, dont la priorisation repose sur le score et le segment. "
                if has_high
                else "Le périmètre est globalement stable, sans signal atypique détecté. "
            )
            + f"L'action recommandée dominante est « {action_label_str} »."
        )
    elif filter_action:
        summary = (
            f"Ce rapport porte sur les clients dont l'action recommandée est « {filter_action_label or filter_action} ». "
            + (
                f"Ce périmètre présente {high_pct} % de clients à risque élevé. "
                if has_high
                else f"Le périmètre est globalement {'stable' if is_stable else 'modéré'}. "
            )
            + "Les indicateurs permettent d'affiner le suivi et la priorisation au sein de ce groupe d'action."
        )
    else:
        summary = (
            f"L'analyse du périmètre filtré identifie {_fmt(total)} clients scorés. "
            "Les indicateurs ci-dessous permettent d'orienter les actions de suivi "
            "sur les profils les plus sensibles du périmètre."
        )

    # ── RISK READING ───────────────────────────────────────────────────────
    if is_global:
        base = f"Le score moyen global {score_interp}. Sur le plan du remboursement, {reimb_interp}. "
        if has_high:
            risk_reading = (
                base
                + "La présence de profils à risque élevé et d'anomalies impose une lecture par segments : "
                "le volume global ne doit pas masquer les poches de risque concentrées. "
                + (
                    "Les clients à risque moyen constituent une zone de transition à surveiller."
                    if has_medium
                    else "La majorité du portefeuille étant stable, l'effort se concentre sur les profils identifiés."
                )
            )
        else:
            risk_reading = (
                base
                + "L'absence de clients à risque élevé confirme la stabilité globale du portefeuille. "
                + (
                    "Les clients à risque moyen représentent la principale zone de surveillance préventive."
                    if has_medium
                    else "Le portefeuille est entièrement composé de profils à risque faible, ce qui constitue une situation favorable."
                )
            )
    elif filter_rt == "low" or (is_very_stable and filter_rt != "high"):
        risk_reading = (
            f"Le score moyen de ce périmètre {score_interp}. "
            f"Sur le plan du remboursement, {reimb_interp}. "
            "Ce périmètre constitue la base stable du portefeuille et peut servir de référence "
            "pour comparer l'évolution des segments plus exposés lors des prochains imports ML."
        )
    elif filter_rt == "high":
        if is_good_payer:
            risk_reading = (
                f"Sur ce périmètre à risque élevé, le score moyen {score_interp}. "
                "Le taux de remboursement est satisfaisant, ce qui nuance la priorisation. "
                "L'enjeu est d'identifier les profils combinant un score élevé et une anomalie détectée."
            )
        else:
            risk_reading = (
                f"Sur ce périmètre à risque élevé, le score moyen {score_interp}. "
                f"Sur le plan du remboursement, {reimb_interp}. "
                "L'enjeu est d'identifier les profils combinant score élevé, anomalie et faible remboursement "
                "pour concentrer l'effort de suivi sur les cas les plus sensibles."
            )
    elif filter_rt == "medium":
        risk_reading = (
            f"Le score moyen de ce périmètre {score_interp}. "
            f"Sur le plan du remboursement, {reimb_interp}. "
            "L'enjeu est d'identifier les profils dont les signaux s'orientent vers le risque élevé "
            "afin d'intervenir avant qu'ils ne basculent dans la zone critique."
        )
    else:
        risk_reading = (
            f"Le score moyen de ce périmètre {score_interp}. "
            f"Sur le plan du remboursement, {reimb_interp}. "
            f"L'action recommandée dominante est « {action_label_str} », "
            "ce qui oriente le pilotage vers les profils les plus sensibles du périmètre sélectionné."
        )

    # ── DECISION SUPPORT — KPI-driven ────────────────────────────────────
    if filter_rt == "low" or is_very_stable:
        ds1 = {
            "priority": "Priorité 1",
            "target": f"Suivi standard{' — ' + seg_label if seg_label else ''}",
            "business_goal": "Maintenir la surveillance de routine",
            "recommended_focus": (
                f"Maintenir le suivi de routine sur ce périmètre{' du segment ' + seg_label if seg_label else ''} stable. "
                "La surveillance périodique permet de détecter toute évolution défavorable."
            ),
        }
        ds2 = {
            "priority": "Priorité 2",
            "target": "Segment de référence comparative",
            "business_goal": "Servir de base comparative",
            "recommended_focus": (
                "Utiliser ce périmètre comme référence comparative pour évaluer "
                "l'exposition des segments plus risqués. "
                "La stabilité observée ici constitue un indicateur de santé du portefeuille."
            ),
        }
        ds3 = {
            "priority": "Priorité 3",
            "target": "Suivi périodique des imports ML",
            "business_goal": "Détecter toute évolution future",
            "recommended_focus": "Suivre l'évolution du score lors des prochains imports ML pour détecter si ce périmètre reste stable.",
        }
    else:
        # Priority 1 based on KPI reality
        if has_high:
            parts1 = [f"Analyser en priorité les profils à risque élevé{' du segment ' + seg_label if seg_label else ''}"]
            if has_anomaly:
                parts1.append(", particulièrement ceux présentant une anomalie.")
            else:
                parts1.append(".")
            if not is_good_payer and not zero_debt:
                parts1.append(" Croiser le score et le remboursement pour affiner la priorisation.")
            ds1 = {
                "priority": "Priorité 1",
                "target": f"Clients à risque élevé{' — ' + seg_label if seg_label else ''}",
                "business_goal": "Réduire l'exposition au risque",
                "recommended_focus": "".join(parts1),
            }
        elif has_anomaly and (filter_anom is True or filter_seg):
            if is_good_payer:
                ds1_focus = (
                    f"Analyser les profils{' ' + seg_label if seg_label else ''} "
                    "présentant une anomalie malgré un taux de remboursement satisfaisant. "
                    "Ces anomalies méritent une vérification contextuelle."
                )
            else:
                ds1_focus = (
                    f"Analyser les profils anomaliques{' du segment ' + seg_label if seg_label else ''} "
                    "en croisant le niveau de risque et le comportement de remboursement."
                )
            ds1 = {
                "priority": "Priorité 1",
                "target": (f"Anomalies — {seg_label}" if seg_label else ("Anomalies à risque moyen" if has_medium else "Anomalies détectées")),
                "business_goal": "Surveiller les signaux atypiques",
                "recommended_focus": ds1_focus,
            }
        elif has_medium:
            ds1 = {
                "priority": "Priorité 1",
                "target": f"Clients à risque moyen{' — ' + seg_label if seg_label else ''}",
                "business_goal": "Prévenir la dégradation",
                "recommended_focus": (
                    f"Surveiller les profils à risque moyen{' du segment ' + seg_label if seg_label else ''} "
                    "afin d'anticiper leur bascule vers le risque élevé."
                    + (" Porter une attention aux clients dont le remboursement se dégrade." if not is_good_payer else "")
                ),
            }
        else:
            ds1 = {
                "priority": "Priorité 1",
                "target": f"Périmètre stable{' — ' + seg_label if seg_label else ''}",
                "business_goal": "Maintenir le suivi standard",
                "recommended_focus": (
                    f"Ce périmètre{' du segment ' + seg_label if seg_label else ''} présente un profil stable. "
                    "Conserver un suivi de routine sans mobiliser prioritairement les ressources métier."
                ),
            }

        # Priority 2
        if has_high and has_anomaly and filter_anom is not True:
            ds2 = {
                "priority": "Priorité 2",
                "target": "Profils avec anomalie",
                "business_goal": "Identifier les signaux cumulatifs",
                "recommended_focus": "Croiser la présence d'anomalie avec le niveau de risque pour identifier les profils concentrant plusieurs signaux défavorables.",
            }
        elif has_high and is_low_reimb and not zero_debt:
            ds2 = {
                "priority": "Priorité 2",
                "target": "Profils à faible remboursement",
                "business_goal": "Renforcer le suivi",
                "recommended_focus": "Identifier les clients à risque élevé dont le taux de remboursement est le plus faible.",
            }
        elif has_high and has_medium:
            ds2 = {
                "priority": "Priorité 2",
                "target": "Clients à risque moyen",
                "business_goal": "Prévenir la dégradation",
                "recommended_focus": "Surveiller les profils à risque moyen afin d'anticiper leur bascule vers le risque élevé.",
            }
        elif has_anomaly and not has_high and is_good_payer:
            ds2 = {
                "priority": "Priorité 2",
                "target": "Cohérence du profil ML",
                "business_goal": "Confirmer la cohérence du classement",
                "recommended_focus": (
                    "Vérifier que les indicateurs de remboursement"
                    + (f" et le classement {seg_label}" if seg_label else "")
                    + " restent cohérents avec le profil habituel de ces clients."
                ),
            }
        elif has_anomaly and not has_high:
            ds2 = {
                "priority": "Priorité 2",
                "target": "Comportement de remboursement",
                "business_goal": "Détecter les signaux de dégradation",
                "recommended_focus": "Surveiller l'évolution du taux de remboursement des profils anomaliques.",
            }
        elif has_medium and not has_high:
            ds2 = {
                "priority": "Priorité 2",
                "target": "Profils à risque moyen sensibles",
                "business_goal": "Identifier les profils les plus exposés",
                "recommended_focus": (
                    "Identifier les clients à risque moyen dont les indicateurs se dégradent "
                    + ("" if is_good_payer else "— notamment le remboursement — ")
                    + "pour intervenir avant une montée en risque."
                ),
            }
        elif filter_anom is False and has_high:
            ds2 = {
                "priority": "Priorité 2",
                "target": "Segments représentés à risque élevé",
                "business_goal": "Orienter le pilotage par segment",
                "recommended_focus": "Comparer les segments présents dans ce périmètre pour identifier les zones de concentration du risque élevé.",
            }
        else:
            ds2 = {
                "priority": "Priorité 2",
                "target": f"Comparaison{' — ' + seg_label if seg_label else ' inter-segments'}",
                "business_goal": "Évaluer le poids du périmètre",
                "recommended_focus": (
                    f"Comparer les indicateurs{' du segment ' + seg_label if seg_label else ' du périmètre'} "
                    "avec les autres segments afin d'évaluer s'il est sur- ou sous-représentatif dans le risque global."
                ),
            }

        # Priority 3
        if has_anomaly and not has_high and is_good_payer:
            ds3 = {
                "priority": "Priorité 3",
                "target": "Suivi périodique",
                "business_goal": "Prévenir une évolution future",
                "recommended_focus": "Suivre l'évolution du score lors des prochains imports pour détecter si l'anomalie persiste ou se résorbe naturellement.",
            }
        elif has_high:
            ds3 = {
                "priority": "Priorité 3",
                "target": "Suivi comparatif inter-segments",
                "business_goal": "Contextualiser le risque",
                "recommended_focus": "Comparer ce périmètre avec le portefeuille global pour évaluer si les zones de risque élevé sont concentrées ou diffuses.",
            }
        else:
            ds3 = {
                "priority": "Priorité 3",
                "target": "Suivi standard",
                "business_goal": "Maintenir la surveillance",
                "recommended_focus": "Conserver un suivi régulier pour détecter rapidement toute évolution défavorable dans ce périmètre.",
            }

    decision_support = [ds1, ds2, ds3]

    # ── MAIN FINDINGS — KPI-conditional ───────────────────────────────────
    if is_global:
        findings = [
            f"Le segment dominant en volume est {dominant_seg}, mais le volume ne doit pas être confondu avec le niveau de risque.",
        ]
        if has_high:
            findings.insert(0, "Le portefeuille est globalement stable, mais une minorité concentre l'essentiel de l'effort de pilotage.")
            if has_anomaly:
                findings.append("Les anomalies détectées deviennent prioritaires lorsqu'elles se combinent avec un risque élevé.")
            if has_medium:
                findings.append("Les clients à risque moyen représentent une zone de transition à surveiller.")
        else:
            findings.insert(0, "L'absence de clients à risque élevé confirme la stabilité globale du portefeuille.")
            if has_medium:
                findings.append("Les clients à risque moyen constituent la principale zone de surveillance préventive.")
            if has_anomaly:
                findings.append("Les anomalies détectées doivent être suivies même en l'absence de risque élevé.")
    elif filter_rt == "low" or is_very_stable:
        findings = [
            f"Ce périmètre{' du segment ' + seg_label if seg_label else ''} présente un profil globalement stable.",
            "L'absence de risque élevé" + (" et d'anomalies" if not has_anomaly else "") + " confirme la maîtrise de ce segment.",
            "Ce périmètre constitue une base de référence utile pour comparer les segments plus exposés.",
            "Un suivi standard suffit à maintenir la surveillance de ce groupe de clients.",
        ]
    elif filter_rt == "high":
        findings = [
            "Ce périmètre concentre les profils nécessitant la plus forte mobilisation des ressources de pilotage.",
            f"L'action dominante « {action_label_str} » doit être appliquée selon les règles métier validées.",
        ]
        if has_anomaly:
            findings.insert(1, "La combinaison risque élevé et anomalie constitue le signal de priorité le plus fort.")
        if not is_good_payer:
            findings.append("Le comportement de remboursement est un indicateur complémentaire pour affiner la priorisation.")
    elif filter_rt == "medium":
        findings = [
            "Le risque moyen représente une zone de transition où la surveillance préventive est déterminante.",
            "Un suivi différencié permet d'intervenir avant que la dégradation ne devienne critique.",
            f"L'action recommandée dominante « {action_label_str} » doit être appliquée de manière ciblée.",
        ]
        if has_anomaly and is_good_payer:
            findings.insert(1, "Les anomalies présentes méritent une vérification contextuelle malgré le remboursement satisfaisant.")
        elif has_anomaly:
            findings.insert(1, "Les profils à risque moyen avec anomalie sont les plus susceptibles de basculer vers le risque élevé.")
    elif filter_anom is True:
        findings = [
            "La présence d'une anomalie constitue un signal d'alerte à croiser avec le niveau de risque et le comportement de remboursement.",
        ]
        if has_high:
            findings.append("Les profils anomaliques à risque élevé concentrent le risque le plus immédiat.")
        if is_good_payer:
            findings.append("Le taux de remboursement satisfaisant rend ces anomalies atypiques — elles peuvent refléter un signal ML provisoire.")
        elif not zero_debt:
            findings.append("Le comportement de remboursement permet de distinguer les anomalies symptomatiques des anomalies passagères.")
        findings.append("Une revue périodique permet de vérifier si l'évolution du score confirme ou invalide le signal initial.")
    elif filter_anom is False:
        findings = [
            "Ce périmètre ne présente aucune anomalie détectée, ce qui simplifie la lecture du risque.",
        ]
        if has_high:
            findings.append("La priorisation repose sur le score de risque, le segment et le comportement de remboursement.")
        else:
            findings.append("Le périmètre sans anomalie constitue un profil lisible, orienté vers un suivi selon le niveau de risque effectif.")
        findings.append("L'absence d'anomalies ne préjuge pas d'une stabilité future — un suivi périodique reste recommandé.")
    elif filter_seg:
        findings = [
            f"Le segment {seg_label} présente une structure de risque spécifique qui mérite une analyse dédiée.",
            "La distribution du risque au sein de ce segment doit être comparée avec celle des autres segments.",
        ]
        if has_high:
            findings.append(f"Les profils à risque élevé du segment {seg_label} sont les cibles prioritaires du pilotage.")
        elif has_anomaly:
            findings.append("Les anomalies détectées dans ce segment constituent le principal signal d'attention à analyser.")
        else:
            findings.append(f"Le segment {seg_label} présente un profil stable dans ce périmètre.")
        if is_good_payer:
            findings.append("Le comportement de remboursement satisfaisant renforce la stabilité apparente, mais ne doit pas exclure un suivi des signaux atypiques.")
        elif not is_good_payer and not zero_debt:
            findings.append("Le comportement de remboursement doit être interprété en tenant compte du contexte propre à ce segment.")
    elif filter_action:
        findings = [
            f"Ce périmètre regroupe les clients dont l'action recommandée est « {filter_action_label or filter_action} ».",
            "La cohérence entre l'action recommandée et les KPIs de risque doit être vérifiée pour chaque profil.",
        ]
        if has_high:
            findings.append("Les profils à risque élevé dans ce périmètre nécessitent un traitement prioritaire.")
        elif is_stable:
            findings.append("Le périmètre est globalement stable, ce qui confirme l'adéquation de l'action recommandée.")
    else:
        findings = [
            "Le périmètre filtré permet une analyse ciblée sur une sous-population spécifique du portefeuille.",
            "La combinaison des signaux (score, anomalie, remboursement) est plus discriminante que chaque indicateur pris isolément.",
            "Une comparaison avec le périmètre global permet d'évaluer si ce sous-ensemble est représentatif ou atypique.",
        ]
        if has_high:
            findings.insert(1, "Les profils à risque élevé restent la cible prioritaire, même dans un périmètre restreint.")

    # ── RECOMMENDATIONS — KPI-conditional ─────────────────────────────────
    if is_global:
        recommendations = [
            "Segmenter le pilotage en trois niveaux : priorité immédiate (risque élevé), surveillance renforcée (risque moyen), suivi standard (risque faible).",
            "Croiser systématiquement le niveau de risque avec les anomalies pour identifier les profils les plus sensibles.",
            "Concentrer les efforts métier sur les segments où le score moyen est le plus élevé.",
        ]
        if has_medium:
            recommendations.append("Surveiller les clients à risque moyen afin d'anticiper une bascule vers le risque élevé.")
        if is_low_reimb and not zero_debt:
            recommendations.append("Renforcer le suivi des clients dont l'encours reste actif malgré un faible taux de remboursement.")
    elif filter_rt == "low" or (is_very_stable and filter_rt != "high"):
        recommendations = [
            "Maintenir le suivi de routine sans mobiliser prioritairement les ressources métier.",
            f"Utiliser ce périmètre{' du segment ' + seg_label if seg_label else ''} comme référence comparative pour les segments plus exposés.",
            "Surveiller l'évolution du score lors des prochains imports pour détecter toute évolution défavorable.",
        ]
        if has_anomaly:
            recommendations.insert(1, "Vérifier si les anomalies éventuelles constituent un signal durable ou ponctuel.")
    elif filter_rt == "high":
        recommendations = [
            "Comparer les segments représentés dans ce périmètre pour identifier les zones de concentration du risque.",
            "Utiliser les rapports filtrés par segment pour affiner l'analyse et orienter les actions de suivi.",
        ]
        if has_anomaly:
            recommendations.insert(0, "Traiter en priorité les profils présentant à la fois un risque élevé et une anomalie détectée.")
        else:
            recommendations.insert(0, "Traiter en priorité les profils présentant les scores de risque les plus élevés.")
        if not is_good_payer and not zero_debt:
            recommendations.append("Renforcer le suivi des clients dont le taux de remboursement est le plus faible.")
    elif filter_rt == "medium":
        recommendations = [
            "Planifier un suivi périodique pour détecter rapidement toute évolution vers le risque élevé.",
            "Comparer les indicateurs de ce périmètre avec ceux du portefeuille global pour évaluer la tendance.",
            "Engager des actions de suivi différenciées selon les segments représentés.",
        ]
        if has_anomaly and is_good_payer:
            recommendations.insert(0, "Analyser les profils à risque moyen présentant une anomalie pour vérifier la cohérence du classement.")
        elif has_anomaly:
            recommendations.insert(0, "Identifier en priorité les profils à risque moyen présentant une anomalie.")
    elif filter_anom is True:
        recommendations = [
            "Croiser les anomalies avec le niveau de risque effectif pour identifier les profils les plus sensibles.",
            "Surveiller l'évolution du score lors des prochains imports pour confirmer ou invalider le signal.",
        ]
        if has_high and not is_good_payer and not zero_debt:
            recommendations.insert(1, "Prioriser les profils cumulant anomalie et risque élevé dans le suivi opérationnel.")
        if not is_good_payer and not zero_debt:
            recommendations.append("Analyser le comportement de remboursement pour distinguer les anomalies symptomatiques des passagères.")
        else:
            recommendations.append("Vérifier si l'anomalie reflète un changement récent ou un signal ML provisoire.")
    elif filter_anom is False:
        recommendations = [
            "Prioriser le pilotage selon le niveau de risque effectif, en l'absence d'anomalie comme signal différenciateur.",
        ]
        if has_high:
            recommendations.insert(0, "Concentrer le suivi sur les profils à risque élevé dont le score est le plus élevé.")
        recommendations.append("Surveiller l'évolution du périmètre lors des prochains imports pour détecter l'apparition d'anomalies.")
        recommendations.append("Utiliser ce périmètre comme comparaison avec le périmètre avec anomalie pour évaluer l'impact du signal ML.")
    elif filter_seg:
        recommendations = [
            "Vérifier si la répartition du risque dans ce segment est conforme à la moyenne du portefeuille.",
            "Utiliser ce rapport comme référence comparative pour suivre l'évolution du segment dans le temps.",
        ]
        if has_high:
            recommendations.insert(0, f"Analyser en priorité les profils à risque élevé du segment {seg_label}.")
        elif has_anomaly:
            recommendations.insert(0, f"Analyser les profils anomaliques du segment {seg_label} pour comprendre la nature du signal ML.")
        else:
            recommendations.insert(0, f"Maintenir un suivi standard du segment {seg_label}.")
        if not is_good_payer and not zero_debt:
            recommendations.append("Comparer les comportements de remboursement au sein du segment pour identifier les profils les plus sensibles.")
    elif filter_action:
        recommendations = [
            f"Vérifier la cohérence entre l'action « {filter_action_label or filter_action} » et le profil réel de chaque client.",
            "Comparer ce périmètre avec le portefeuille global pour évaluer la représentativité de cette action.",
            "Suivre l'évolution des indicateurs lors des prochains imports pour ajuster l'action recommandée si nécessaire.",
        ]
        if has_high:
            recommendations.insert(0, "Traiter en priorité les profils à risque élevé dans ce périmètre d'action.")
    else:
        recommendations = [
            "Croiser les signaux disponibles (score, anomalie, remboursement) pour affiner la priorisation.",
            "Comparer ce périmètre avec le portefeuille global pour évaluer s'il est sur- ou sous-représentatif du risque.",
            "Concentrer les ressources sur les combinaisons de signaux les plus défavorables.",
        ]
        if has_high:
            recommendations.insert(0, "Prioriser l'analyse des profils à risque élevé du périmètre filtré.")

def build_global_decision_context(kpis: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
    """
    Python builds the deterministic business logic for decision support.
    Qwen will only write the narrative around these decisions.
    """
    total = int(kpis.get("total_clients") or 0)
    high = int(kpis.get("clients_high") or 0)
    medium = int(kpis.get("clients_medium") or 0)
    low = int(kpis.get("clients_low") or 0)
    anomaly = int(kpis.get("clients_with_anomaly") or 0)
    avg_debt = kpis.get("average_debt")
    avg_reimb = kpis.get("average_reimbursement_ratio")
    
    risk_filter = filters.get("risk_tier")
    seg_filter = filters.get("cluster_name")
    anomaly_filter = filters.get("is_anomaly")
    action_filter = filters.get("recommended_action")
    search_filter = filters.get("search")
    
    is_global = not filters
    is_search = bool(search_filter)
    is_empty = total == 0
    
    context = {
        "report_scope": "search" if is_search else "empty" if is_empty else "filtered" if not is_global else "global",
        "risk_posture": "Stabilité" if low == total else "Surveillance" if high == 0 else "Prioritaire",
        "priority_level": "Normal" if high == 0 else "Élevé",
        "main_focus": "Maintenance" if low == total else "Prévention" if high == 0 else "Diminution de l'exposition",
        "business_goal": "Consolider la base stable" if low == total else "Éviter la dégradation" if high == 0 else "Traiter les cas critiques",
        "decision_support_base": [],
        "recommendation_guidelines": []
    }
    
    # 1. Decision Support Base (Deterministic Priorities)
    def add_card(priority_num: int, title: str, target: str, goal: str, focus: str):
        context["decision_support_base"].append({
            "priority": f"Priorité {priority_num} — {title}",
            "target": target,
            "business_goal": goal,
            "recommended_focus": focus
        })

    if is_empty:
        add_card(1, "Ajuster les filtres", "Aucun résultat", "Élargir le périmètre", "Modifier les critères pour obtenir un périmètre exploitable.")
    elif is_search:
        add_card(1, "Vérifier les profils", f"{total} clients trouvés", "Analyse ciblée", "Vérifier les scores et situations individuelles.")
        add_card(2, "Comparer les situations", "Résultats de recherche", "Aide au choix d'action", "Comparer les profils avant de décider du suivi.")
        add_card(3, "Accéder au détail", "Profils sélectionnés", "Lecture fine", "Ouvrir la fiche client ou générer le rapport individuel.")
    elif is_global:
        add_card(1, "Risque élevé", f"{high} clients", "Réduire l'exposition", "Traiter les profils les plus exposés (score élevé, segment sensible).")
        add_card(2, "Risque moyen", f"{medium} clients", "Prévention dégradation", "Surveiller l'évolution du score et du remboursement.")
        add_card(3, "Risque faible", f"{low} clients", "Maintenir stabilité", "Conserver un suivi routine sur la base stable.")
    elif risk_filter == "high":
        add_card(1, "Suivi prioritaire", f"{total} clients à risque élevé", "Diminution du risque", "Classer par score et remboursement pour traiter les cas sensibles.")
        if action_filter == "call_center_priority":
            add_card(2, "Contact CRC", "Action dominante", "Qualification situation", "Utiliser l'Appel prioritaire centre de relation client pour agir sur ce périmètre.")
        else:
            add_card(2, "Priorisation", "Score & Segment", "Cibler l'effort", "Isoler les clients dont le remboursement est le moins régulier.")
        add_card(3, "Comparaison", "Périmètre global", "Affiner pilotage", "Comparer ce groupe à risque élevé avec la tendance globale du portefeuille.")
    elif risk_filter == "medium":
        add_card(1, "Surveillance renforcée", f"{total} clients à risque moyen", "Prévenir la dégradation", "Suivre l'évolution du score et du comportement de remboursement.")
        if action_filter == "sms_retention_offer":
            add_card(2, "SMS personnalisé", "Action dominante", "Contact préventif", "Accompagner les clients par un suivi léger avant toute dégradation.")
        else:
            add_card(2, "Prévention", "Évolution score", "Anticiper risque", "Détecter les profils dont le signal devient défavorable.")
        add_card(3, "Focus segment", "Population filtrée", "Cibler prévention", "Identifier les concentrations de risque moyen par segment.")
    elif risk_filter == "low":
        add_card(1, "Suivi routine", f"{total} clients à risque faible", "Maintenir stabilité", "Conserver une surveillance périodique standard sans priorité forte.")
        add_card(2, "Base comparative", "Segment stable", "Repère de performance", "Utiliser ce groupe comme référence de stabilité pour le pilotage global.")
        add_card(3, "Surveillance", "Périodicité standard", "Maintenir maîtrise", "Vérifier si certains profils quittent le risque faible lors du prochain cycle.")
    elif seg_filter == "Bon-payeur" and (avg_debt == 0 or (avg_reimb is not None and float(avg_reimb) >= 0.95)):
        add_card(1, "Maintenir stabilité", "Segment Bon payeur", "Consolider la base", "Conserver un suivi léger et routine sur cette population stable.")
        if anomaly_filter is True:
            add_card(2, "Vérification prudente", "Signal d'anomalie", "Éviter erreur de tri", "Vérifier si l'anomalie est passagère sans dramatiser le risque.")
        else:
            add_card(2, "Surveillance standard", "Aucune anomalie", "Suivi périodique", "Réévaluer les indicateurs lors du prochain cycle d'analyse.")
        add_card(3, "Comparaison", "Portefeuille global", "Situer performance", "Comparer la solidité de ce segment avec les autres populations.")
    elif seg_filter == "SUSPENDED":
        add_card(1, "Attention ciblée", "Segment Suspendu", "Qualification risque", "Analyser si le score élevé justifie une action prioritaire immédiate.")
        add_card(2, "Signaux croisés", "Score & Dette", "Priorisation", "Distinguer les profils critiques des cas de surveillance standard.")
    elif seg_filter == "DISCONNECTED":
        add_card(1, "Suivi prioritaire", "Segment Déconnecté", "Récupération encours", "Agir prioritairement si le score de risque et la dette sont élevés.")
        add_card(2, "Ciblage", "Remboursement", "Efficacité action", "Cibler les clients dont l'historique de remboursement est le moins régulier.")
    elif seg_filter == "ON-HOLD":
        add_card(1, "Suivi de transition", "Segment En attente", "Surveillance future", "Observer l'évolution du risque avant toute décision lourde.")
        add_card(2, "Vérification", "Mise à jour ML", "Confirmer tendance", "Attendre le prochain cycle pour confirmer le niveau de risque effectif.")
    elif anomaly_filter is True:
        add_card(1, "Signal de tri", f"{anomaly} anomalies", "Surveillance ciblée", "Utiliser l'anomalie pour isoler les profils atypiques méritant vérification.")
        add_card(2, "Croisement signaux", "Score & Segment", "Prioriser", "Traiter prioritairement si l'anomalie se combine à un risque déjà élevé.")
        add_card(3, "Validation", "Détail client", "Confirmer signal", "Vérifier le contexte de l'anomalie au cas par cas.")
    else:
        # Default filtered context
        add_card(1, "Pilotage ciblé", f"{total} clients sélectionnés", "Optimiser ressources", "Traiter selon le risque effectif et l'action recommandée.")
        add_card(2, "Analyse signaux", "Score & Remboursement", "Priorisation fine", "Croiser les indicateurs pour identifier les cas les plus sensibles.")
        add_card(3, "Comparaison", "Périmètre global", "Situer le risque", "Comparer ce groupe à la tendance globale du portefeuille.")

    # 2. Recommendation Guidelines
    if is_empty:
        context["recommendation_guidelines"].append("Réinitialiser les filtres pour obtenir des données.")
    elif is_search:
        context["recommendation_guidelines"].extend(["Vérifier chaque profil individuellement.", "Ne pas généraliser à tout le portefeuille."])
    elif risk_filter == "high":
        context["recommendation_guidelines"].extend(["Traitement prioritaire requis.", "Focus sur score élevé et remboursement faible."])
    elif risk_filter == "low":
        context["recommendation_guidelines"].extend(["Maintenir suivi routine.", "Pas d'urgence.", "Pas de priorité forte."])
    elif action_filter == "sms_retention_offer":
        context["recommendation_guidelines"].extend(["Suivi léger par SMS.", "Pas d'offre commerciale.", "Pas de remise."])
    elif action_filter == "call_center_priority":
        context["recommendation_guidelines"].extend(["Contact ciblé par centre d'appel.", "Pas de menace.", "Pas de sanction."])

    return context


def _global_report_prompt_legacy_unused(kpis: dict[str, Any], active_filters: dict[str, Any], decision_context: dict[str, Any]) -> str:
    compact_kpis = json.dumps(kpis, ensure_ascii=False, default=str, separators=(",", ":"))
    compact_filters = json.dumps(_filter_labels_for_prompt(active_filters), ensure_ascii=False, default=str, separators=(",", ":"))
    compact_decision = json.dumps(decision_context, ensure_ascii=False, default=str, separators=(",", ":"))
    
    is_global = not active_filters
    filter_rt = active_filters.get("risk_tier")
    filter_seg = active_filters.get("cluster_name")
    filter_anom = active_filters.get("is_anomaly")
    filter_action = active_filters.get("recommended_action")

    if is_global:
        scope_instruction = (
            "Ce rapport couvre l'ensemble du portefeuille. "
            "Il doit présenter une vision stratégique globale avec une priorisation en trois niveaux. "
            "IMPORTANT: Ne jamais utiliser le mot 'API'. Ne jamais utiliser le mot 'réduction'. "
            "Ne jamais proposer de remise, bonus, cadeau ou offre commerciale."
        )
    elif filter_rt == "high" and filter_anom is False:
        scope_instruction = (
            "Ce rapport couvre uniquement des profils à risque élevé sans anomalie détectée. "
            "Ne jamais présenter l'anomalie comme facteur de priorité. "
            "Expliquer que la priorité vient du score, du remboursement et du profil client."
        )
    elif filter_rt == "high":
        scope_instruction = (
            "Ce rapport couvre uniquement les profils à risque élevé. "
            "Tous les éléments du rapport doivent être orientés vers ce périmètre. "
            "Ne pas parler de risque faible comme priorité."
        )
    elif filter_rt == "medium":
        scope_instruction = (
            "Ce rapport couvre les profils à risque moyen. "
            "Insister sur la prévention de la dégradation vers le risque élevé."
        )
    elif filter_seg:
        seg_label = _SEGMENT_LABELS_FR.get(filter_seg, filter_seg)
        scope_instruction = (
            f"Ce rapport porte sur le segment {seg_label}. "
            "Adapter toutes les recommandations à ce segment spécifique."
        )
    elif filter_anom is True:
        scope_instruction = (
            "Ce rapport couvre les profils avec anomalie détectée. "
            "Insister sur la combinaison anomalie, score et remboursement."
        )
    elif filter_anom is False:
        scope_instruction = (
            "Ce rapport couvre des profils sans anomalie détectée. "
            "Ne jamais recommander de croiser les anomalies et ne jamais écrire 'signal atypique'. "
            "Expliquer que le pilotage repose sur le score, le remboursement, le segment et l'action recommandée."
        )
    else:
        scope_instruction = (
            "Ce rapport couvre un périmètre filtré. "
            "Adapter le contenu aux filtres actifs fournis."
        )

    # Build KPI-specific anti-contradiction constraints
    kpi_constraints: list[str] = []
    kpi_high = int(kpis.get("clients_high") or 0)
    kpi_reimb = kpis.get("average_reimbursement_ratio")
    kpi_debt = kpis.get("average_debt")
    filter_action = (active_filters or {}).get("recommended_action")
    dominant_action = str(kpis.get("dominant_recommended_action") or "")
    filter_rt = (active_filters or {}).get("risk_tier")
    
    if active_filters and "portefeuille" in combined_text_lower:
        allowed_comparison = (
            "portefeuille global" in combined_text_lower
            or "comparaison avec le portefeuille" in combined_text_lower
            or "comparer ce pÃ©rimÃ¨tre" in combined_text_lower
            or "comparer ce périmètre" in combined_text_lower
        )
        if not allowed_comparison:
            errors.append("forbidden_term:portefeuille_in_filtered")
        if "100 % du portefeuille" in combined_text_lower or "100% du portefeuille" in combined_text_lower:
            errors.append("forbidden_term:100_percent_portefeuille_in_filtered")
    if kpi_high == 0:
        kpi_constraints.append(
            "INTERDIT car clients_high=0 : ne jamais écrire 'risque élevé', "
            "'cas les plus critiques', 'profils à la fois anomaliques et à risque élevé'."
        )
    if kpi_reimb is not None and float(kpi_reimb) >= 0.95:
        kpi_constraints.append(
            f"INTERDIT car taux_remboursement={round(float(kpi_reimb)*100)} % : "
            "ne jamais écrire 'faible remboursement', 'remboursement dégradé', "
            "'comportement de remboursement faible'."
        )
    if kpi_debt is not None and float(kpi_debt) == 0:
        kpi_constraints.append(
            "INTERDIT car dette_moyenne=0 : "
            "ne jamais écrire 'encours actif', 'exposition financière', 'dette active'."
        )
    if filter_anom is False:
        kpi_constraints.append(
            "INTERDIT car filtre sans anomalie : ne jamais écrire 'avec anomalie', 'signal atypique', "
            "'profils combinant risque et anomalie', ni recommander de croiser les anomalies. "
            "Phrase autorisée : 'Aucune anomalie n'est détectée dans ce périmètre'."
        )
    if filter_action == "sms_retention_offer":
        kpi_constraints.append(
            "INTERDIT car action SMS personnalisé : ne jamais écrire remise, bonus, réduction, offre commerciale ou cadeau."
        )
    if active_filters:
        kpi_constraints.append(
            "INTERDIT : ne jamais utiliser le mot 'portefeuille' ou l'expression '100 % du portefeuille'. "
            "Utiliser exclusivement les termes 'périmètre filtré' ou 'périmètre sélectionné'."
        )
    kpi_constraints_str = (" ".join(kpi_constraints) + " ") if kpi_constraints else ""

    return (
        "Rôle: rédacteur métier Bad Debts. Tu rédiges uniquement; tu ne décides rien. "
        "IMPORTANT: Tu reçois une aide à la décision déjà construite par Python (decision_support_base). "
        "Tu DOIS la respecter strictement dans ta réponse JSON, clé 'decision_support'. "
        "Tu ne changes ni les priorités, ni les cibles, ni les objectifs, ni le focus recommandé. "
        "Réponds en français, direct et court. "
        f"Contexte: {scope_instruction} "
        "Structure JSON stricte: "
        "report_title string; executive_summary string (max 3 phrases); risk_reading string (max 2 phrases); "
        "business_rationale array string; decision_support array objects (COPIER decision_support_base); "
        "main_findings array string; business_recommendations array objects {title,why,example,expected_impact}; "
        "profile_recommendations array string. "
        f"Contraintes: {kpi_constraints_str} "
        f"AIDE À LA DÉCISION PYTHON: {compact_decision}. "
        f"KPIs: {compact_kpis}. FILTRES: {compact_filters}."
    )


def _global_report_prompt(kpis: dict[str, Any], active_filters: dict[str, Any], decision_context: dict[str, Any]) -> str:
    total = int(kpis.get("total_clients") or 0)
    compact_context = {
        "titre_python": _global_report_title(active_filters, total),
        "kpis": {
            "total_clients": total,
            "clients_high": int(kpis.get("clients_high") or 0),
            "clients_medium": int(kpis.get("clients_medium") or 0),
            "clients_low": int(kpis.get("clients_low") or 0),
            "clients_with_anomaly": int(kpis.get("clients_with_anomaly") or 0),
            "average_risk_score": kpis.get("average_risk_score"),
            "average_debt": kpis.get("average_debt"),
            "average_reimbursement_ratio": kpis.get("average_reimbursement_ratio"),
            "dominant_segment": kpis.get("dominant_segment"),
            "dominant_recommended_action": kpis.get("dominant_recommended_action"),
        },
        "filtres": _filter_labels_for_prompt(active_filters),
        "decision_context": {
            "report_scope": decision_context.get("report_scope"),
            "risk_posture": decision_context.get("risk_posture"),
            "priority_level": decision_context.get("priority_level"),
            "main_focus": decision_context.get("main_focus"),
            "business_goal": decision_context.get("business_goal"),
            "decision_support_base": (decision_context.get("decision_support_base") or [])[:3],
            "recommendation_guidelines": (decision_context.get("recommendation_guidelines") or [])[:4],
        },
        "recommandations_python": _global_structured_business_recommendations(kpis, active_filters)[:3],
    }
    compact = json.dumps(compact_context, ensure_ascii=False, default=str, separators=(",", ":"))
    scope_instruction = (
        "Si un filtre est actif, utilise les termes périmètre filtré, périmètre sélectionné ou groupe sélectionné. "
        "Ne présente jamais un périmètre filtré comme tout le portefeuille. "
        "Le mot portefeuille est autorisé seulement pour une comparaison explicite avec le portefeuille global."
        if active_filters
        else "Ce rapport couvre le portefeuille global."
    )
    return (
        "Tu es rédacteur métier Bad Debts. Python a déjà calculé les KPIs, filtres, risques, actions, priorités, graphes et recommandations. "
        "Tu rédiges uniquement trois textes courts en français; tu ne calcules rien et tu ne décides rien. "
        "Réponds seulement avec un objet JSON contenant exactement: "
        "decision_summary string max 3 phrases; risk_reading string max 3 phrases; business_recommendations_narrative string max 4 phrases. "
        "Interdits: chiffres inventés, décision nouvelle, priorité nouvelle, action nouvelle, remise, réduction, bonus, cadeau, "
        "offre commerciale, promotion, sanction, menace, contentieux, poursuite, API, JSON, backend, frontend, Ollama, Qwen, LLM, modèle IA. "
        f"{scope_instruction} "
        f"CONTEXTE:{compact}"
    )


def _split_sentences(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[.!?]+", str(value or "")) if part.strip()]


def validate_fast_ai_narrative(
    report_ai: dict[str, Any] | None,
    kpis: dict[str, Any],
    active_filters: dict[str, Any] | None = None,
    decision_context: dict[str, Any] | None = None,
) -> list[str]:
    """
    Validate the 3 narrative fields from the fast AI report.
    """
    if not isinstance(report_ai, dict):
        return ["empty_or_invalid_json"]

    errors: list[str] = []
    field_limits = {
        "decision_summary": 3,
        "risk_reading": 3,
        "business_recommendations_narrative": 4,
    }
    
    combined_text = ""
    for field, max_sentences in field_limits.items():
        val = report_ai.get(field)
        if not isinstance(val, str) or not val.strip():
            errors.append(f"missing_or_empty_field:{field}")
        elif len(_split_sentences(val)) > max_sentences:
            errors.append(f"too_many_sentences:{field}")
        elif len(val) > 900:
            errors.append(f"text_too_long:{field}")
        else:
            combined_text += " " + val.strip()

    if errors:
        return errors

    combined_text_lower = combined_text.lower()

    # 1. Forbidden terms (Technical & Business)
    for term in _GLOBAL_TECHNICAL_FORBIDDEN:
        if _contains_forbidden_term(combined_text_lower, term):
            errors.append(f"forbidden_technical_term:{term}")
    
    for term in _GLOBAL_BUSINESS_FORBIDDEN:
        if term in combined_text_lower:
            errors.append(f"forbidden_business_term:{term}")

    for phrase in _PHRASES_FORBIDDEN_GLOBAL:
        if phrase in combined_text_lower:
            errors.append(f"forbidden_phrase:{phrase}")

    # 2. Complete MSISDN check
    if re.search(r'\b2\d{8,}\b', combined_text):
        errors.append("complete_msisdn_detected")

    # 3. Number validation (Anti-hallucination)
    allowed_numbers = _allowed_global_numbers(kpis)
    if not _generated_numbers_are_allowed(combined_text, allowed_numbers):
        errors.append("hallucinated_numbers_detected")

    # 4. Logical contradictions (KPI-driven)
    kpi_high = int(kpis.get("clients_high") or 0)
    kpi_anomaly = int(kpis.get("clients_with_anomaly") or 0)
    kpi_reimb = kpis.get("average_reimbursement_ratio")
    kpi_debt = kpis.get("average_debt")
    filter_action = (active_filters or {}).get("recommended_action")
    dominant_action = str(kpis.get("dominant_recommended_action") or "")
    filter_rt = (active_filters or {}).get("risk_tier")
    
    if active_filters and "portefeuille" in combined_text_lower:
        allowed_comparison = (
            "portefeuille global" in combined_text_lower
            or "comparaison avec le portefeuille" in combined_text_lower
            or "comparer ce pÃ©rimÃ¨tre" in combined_text_lower
            or "comparer ce périmètre" in combined_text_lower
        )
        if not allowed_comparison:
            errors.append("forbidden_term:portefeuille_in_filtered")
        if "100 % du portefeuille" in combined_text_lower or "100% du portefeuille" in combined_text_lower:
            errors.append("forbidden_term:100_percent_portefeuille_in_filtered")
    
    if kpi_high == 0:
        if "risque élevé" in combined_text_lower:
            allowed_neg = ["aucun client à risque élevé", "absence de clients à risque élevé", "pas de risque élevé"]
            if not any(a in combined_text_lower for a in allowed_neg):
                errors.append("contradiction:mentions_high_risk_but_kpi_is_0")
    
    if kpi_high == 0 and any(term in combined_text_lower for term in ("traitement prioritaire", "appel prioritaire", "urgence", "priorisation forte")):
        errors.append("contradiction:priority_without_high")
    if kpi_high == 0 and "risque élevé" in combined_text_lower:
        allowed_neg = ("aucun client à risque élevé", "absence de clients à risque élevé", "pas de risque élevé")
        if not any(term in combined_text_lower for term in allowed_neg):
            errors.append("contradiction:mentions_high_risk_but_kpi_is_0")

    if kpi_anomaly == 0:
        if "anomalie" in combined_text_lower:
            allowed_neg = ["aucune anomalie", "absence d'anomalie", "sans anomalie"]
            if not any(a in combined_text_lower for a in allowed_neg):
                errors.append("contradiction:mentions_anomaly_but_kpi_is_0")

    if kpi_reimb is not None and float(kpi_reimb) >= 0.95:
        if "faible remboursement" in combined_text_lower or "remboursement dégradé" in combined_text_lower:
            errors.append("contradiction:mentions_low_reimbursement_but_kpi_is_high")

    if kpi_debt is not None and float(kpi_debt) == 0:
        if any(term in combined_text_lower for term in ("dette active", "encours actif", "exposition financiÃ¨re", "exposition financière", "montant Ã  recouvrer", "montant à recouvrer")):
            errors.append("contradiction:mentions_active_debt_but_kpi_is_0")

    if filter_action == "monitor_only" or dominant_action == "monitor_only":
        if any(term in combined_text_lower for term in ("appel prioritaire", "traitement prioritaire", "urgence")):
            errors.append("contradiction:monitor_only_action")
    if filter_action == "sms_retention_offer":
        if any(term in combined_text_lower for term in ("remise", "rÃ©duction", "réduction", "offre commerciale", "bonus", "cadeau", "promotion")):
            errors.append("contradiction:sms_commercial_term")
    if filter_rt == "low" and any(term in combined_text_lower for term in ("urgence", "critique", "priorisation forte")):
        errors.append("contradiction:low_risk_filter")

    return errors


def _normalize_global_report(raw: dict[str, Any]) -> dict[str, Any]:
    def _str(v: Any, default: str = "") -> str:
        return str(v or default).strip()

    return {
        "decision_summary": _str(raw.get("decision_summary")),
        "risk_reading": _str(raw.get("risk_reading")),
        "business_recommendations_narrative": _str(raw.get("business_recommendations_narrative")),
    }


def _sanitize_fast_ai_narrative(report_ai: dict[str, Any]) -> dict[str, Any]:
    replacements = {
        "sans priorisation forte": "avec un suivi proportionné",
        "sans priorité forte": "avec un suivi proportionné",
        "menace significative": "point de vigilance important",
        "menaces significatives": "points de vigilance importants",
        "menace": "point de vigilance",
        "menaces": "points de vigilance",
    }
    cleaned = dict(report_ai)
    for field in ("decision_summary", "risk_reading", "business_recommendations_narrative"):
        value = cleaned.get(field)
        if not isinstance(value, str):
            continue
        for bad, replacement in replacements.items():
            value = re.sub(rf"\b{re.escape(bad)}\b", replacement, value, flags=re.IGNORECASE)
        cleaned[field] = value
    return cleaned


def _global_report_validation_errors(
    report: dict[str, Any] | None,
    kpis: dict[str, Any],
    active_filters: dict[str, Any] | None = None,
    decision_context: dict[str, Any] | None = None,
) -> list[str]:
    if not isinstance(report, dict):
        return ["empty_or_invalid_json"]

    errors: list[str] = []
    for field in _GLOBAL_REPORT_REQUIRED_FIELDS:
        if field not in report:
            errors.append(f"missing_field:{field}")

    for field in ("report_title", "executive_summary", "risk_reading"):
        value = report.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > 1600:
            errors.append(f"invalid_text:{field}")

    min_recommendations = 1 if int(kpis.get("total_clients") or 0) == 0 else 2
    recs = report.get("business_recommendations")
    if not isinstance(recs, list) or not (min_recommendations <= len(recs) <= 4):
        errors.append("invalid_business_recommendations_count")
    else:
        for index, rec in enumerate(recs, start=1):
            if isinstance(rec, str) and rec.strip():
                continue
            if not isinstance(rec, dict):
                errors.append(f"invalid_business_recommendation:{index}")
                continue
            for field in ("title", "why", "example", "expected_impact"):
                value = rec.get(field)
                if not isinstance(value, str) or not value.strip() or len(value) > 600:
                    errors.append(f"invalid_business_recommendation:{index}:{field}")

    if not _valid_string_list(report.get("main_findings"), min_len=2, max_len=8):
        errors.append("invalid_main_findings")
    if not _valid_string_list(report.get("profile_recommendations"), min_len=2, max_len=6):
        errors.append("invalid_profile_recommendations")
    if not _valid_string_list(report.get("business_rationale"), min_len=2, max_len=6):
        errors.append("invalid_business_rationale")

    decision_support = report.get("decision_support")
    errors.extend(_decision_support_validation_errors(decision_support, kpis, active_filters, decision_context))

    combined = json.dumps(report, ensure_ascii=False, default=str).lower()
    narrative = json.dumps(
        {
            "report_title": report.get("report_title"),
            "executive_summary": report.get("executive_summary"),
            "risk_reading": report.get("risk_reading"),
            "business_rationale": report.get("business_rationale"),
            "decision_support": report.get("decision_support"),
            "main_findings": report.get("main_findings"),
            "business_recommendations": report.get("business_recommendations"),
            "profile_recommendations": report.get("profile_recommendations"),
        },
        ensure_ascii=False,
        default=str,
    ).lower()

    # Terminology check for "portefeuille" in filtered reports
    if active_filters:
        # Ban "portefeuille" unless it's explicitly "portefeuille global" for comparison
        if "portefeuille" in narrative:
            # Check if it's an allowed comparison
            has_comparison = "portefeuille global" in narrative or "comparaison avec le portefeuille global" in narrative
            if not has_comparison:
                errors.append("forbidden_term:portefeuille_in_filtered")
        
        # Ban "100 % du portefeuille" even if comparison is present if it's used to describe the current scope
        if "100 % du portefeuille" in narrative or "100% du portefeuille" in narrative:
            errors.append("forbidden_term:100_percent_portefeuille_in_filtered")

    forbidden_technical = [term for term in _GLOBAL_TECHNICAL_FORBIDDEN if _contains_forbidden_term(combined, term)]
    forbidden_business = [term for term in _GLOBAL_BUSINESS_FORBIDDEN if term in combined]
    forbidden_phrases = [phrase for phrase in _PHRASES_FORBIDDEN_GLOBAL if phrase in combined]
    if forbidden_technical:
        errors.append("technical_terms:" + ",".join(forbidden_technical[:3]))
    if forbidden_business:
        errors.append("business_forbidden:" + ",".join(forbidden_business[:3]))
    if forbidden_phrases:
        errors.append("weak_phrases:" + ",".join(forbidden_phrases[:3]))

    if re.search(r'\b2\d{8,}\b', combined):
        errors.append("complete_msisdn")
    if not _generated_numbers_are_allowed(_global_report_number_narrative(report), _allowed_global_numbers(kpis)):
        errors.append("invented_number")

    kpi_high = int(kpis.get("clients_high") or 0)
    kpi_medium = int(kpis.get("clients_medium") or 0)
    kpi_anomaly = int(kpis.get("clients_with_anomaly") or 0)
    kpi_reimb = kpis.get("average_reimbursement_ratio")
    kpi_debt = kpis.get("average_debt")
    kpi_score = kpis.get("average_risk_score")
    kpi_total = int(kpis.get("total_clients") or 0)
    seg_filter = (active_filters or {}).get("cluster_name")
    anomaly_filter = (active_filters or {}).get("is_anomaly")
    filter_rt = (active_filters or {}).get("risk_tier")
    filter_action = (active_filters or {}).get("recommended_action")

    if any(raw in combined for raw in ("risk_tier=", "cluster_name=", "is_anomaly=", "recommended_action=")):
        errors.append("raw_filter_name_visible")
    if kpi_high == 0:
        if "risque élevé" in narrative:
            allowed = ("aucun client à risque élevé", "absence de clients à risque élevé", "aucun profil à risque élevé", "risque élevé n'est présent")
            if not any(p in narrative for p in allowed):
                errors.append("contradiction:clients_high=0")
        if any(t in narrative for t in ("profils critiques", "cas critiques", "priorité élevée", "urgence", "priorisation forte")):
            errors.append("contradiction:clients_high=0:priority")
    if kpi_medium == 0 and any(t in narrative for t in ("zone de transition", "bascule vers le risque élevé", "risque moyen vers le risque élevé")):
        errors.append("contradiction:clients_medium=0")
    if kpi_anomaly == 0:
        if any(t in narrative for t in ("anomalies à traiter", "croiser les anomalies", "signal atypique", "avec anomalie", "profils combinant risque et anomalie")):
            errors.append("contradiction:clients_with_anomaly=0")
    if kpi_reimb is not None and float(kpi_reimb) >= 0.95:
        if any(t in narrative for t in ("faible remboursement", "remboursement dégradé", "comportement de remboursement faible", "retard de remboursement", "remboursement moins régulier")):
            errors.append("contradiction:average_reimbursement_ratio>=95")
    if kpi_debt is not None and float(kpi_debt) == 0:
        if any(t in narrative for t in ("encours actif", "exposition financière", "dette active", "montant à recouvrer")):
            errors.append("contradiction:average_debt=0")
    if filter_rt == "low" and any(t in narrative for t in ("urgence", "critique", "priorisation forte")):
        errors.append("contradiction:low_filter")
    if filter_action == "monitor_only" and any(t in narrative for t in ("traitement prioritaire", "appel prioritaire", "urgence")):
        errors.append("contradiction:monitor_only")
    if kpi_total > 0 and kpi_high == kpi_total and kpi_score is not None and float(kpi_score) >= 0.70:
        if any(t in narrative for t in ("périmètre stable", "globalement stable", "suivi routine", "risque faible")):
            errors.append("contradiction:all_high_stable")
    if kpi_total == 0:
        empty_forbidden = (
            "suivi routine",
            "risque élevé",
            "risque moyen",
            "appel prioritaire",
            "sms personnalisé",
            "surveiller les clients",
            "prioriser les clients",
            "suivi standard",
            "clients à risque",
            "anomalies à croiser",
        )
        rec_text = json.dumps(report.get("business_recommendations") or [], ensure_ascii=False, default=str).lower()
        for term in empty_forbidden:
            if term in rec_text:
                errors.append(f"contradiction:empty_recommendation:{term}")
    if (
        seg_filter == "Bon-payeur"
        and anomaly_filter is True
        and kpi_high == 0
        and kpi_debt is not None
        and float(kpi_debt) == 0
        and kpi_reimb is not None
        and float(kpi_reimb) >= 0.95
    ):
        stable_bon_payeur_forbidden = (
            "surveiller de près",
            "profils exposés",
            "profils sensibles",
            "remboursement faible",
            "dette active",
            "exposition financière",
        )
        for term in stable_bon_payeur_forbidden:
            if term in narrative:
                errors.append(f"contradiction:bon_payeur_anomaly_stable:{term}")
        if (
            "traitement prioritaire" in narrative
            and "sans traitement prioritaire" not in narrative
            and "ne pas mobiliser un traitement prioritaire" not in narrative
        ):
            errors.append("contradiction:bon_payeur_anomaly_stable:traitement prioritaire")

    return errors


def _validate_global_report(report: dict[str, Any], kpis: dict[str, Any], active_filters: dict[str, Any] | None = None, decision_context: dict[str, Any] | None = None) -> bool:
    if _global_report_validation_errors(report, kpis, active_filters, decision_context):
        return False
    import re
    if not isinstance(report, dict):
        return False
    if any(f not in report for f in _GLOBAL_REPORT_REQUIRED_FIELDS):
        return False

    for field in ("report_title", "executive_summary", "risk_reading"):
        value = report.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > 1600:
            return False

    if not _valid_string_list(report.get("main_findings"), min_len=2, max_len=8):
        return False
    
    min_recommendations = 1 if int(kpis.get("total_clients") or 0) == 0 else 2
    recs = report.get("business_recommendations")
    if not isinstance(recs, list) or not (min_recommendations <= len(recs) <= 4):
        return False
    for rec in recs:
        if isinstance(rec, str):
            if not rec.strip():
                return False
        elif isinstance(rec, dict):
            for field in ("title", "why", "example", "expected_impact"):
                value = rec.get(field)
                if not isinstance(value, str) or not value.strip() or len(value) > 600:
                    return False
        else:
            return False

    if not _valid_string_list(report.get("profile_recommendations"), min_len=2, max_len=6):
        return False
    if not _valid_string_list(report.get("business_rationale"), min_len=2, max_len=6):
        return False

    decision_support = report.get("decision_support")
    if _decision_support_validation_errors(decision_support, kpis, active_filters, decision_context):
        return False

    combined = json.dumps(report, ensure_ascii=False, default=str).lower()
    narrative = json.dumps(
        {
            "report_title": report.get("report_title"),
            "executive_summary": report.get("executive_summary"),
            "risk_reading": report.get("risk_reading"),
            "business_rationale": report.get("business_rationale"),
            "decision_support": report.get("decision_support"),
            "main_findings": report.get("main_findings"),
            "business_recommendations": report.get("business_recommendations"),
            "profile_recommendations": report.get("profile_recommendations"),
        },
        ensure_ascii=False,
        default=str,
    ).lower()

    if any(_contains_forbidden_term(combined, term) for term in _GLOBAL_TECHNICAL_FORBIDDEN):
        return False
    if any(term in combined for term in _GLOBAL_BUSINESS_FORBIDDEN):
        return False
    if any(phrase in combined for phrase in _PHRASES_FORBIDDEN_GLOBAL):
        return False

    if re.search(r'\b2\d{8,}\b', combined):
        return False
    if not _generated_numbers_are_allowed(_global_report_number_narrative(report), _allowed_global_numbers(kpis)):
        return False

    # Anti-contradiction — text must not contradict actual KPI values
    kpi_high = int(kpis.get("clients_high") or 0)
    kpi_medium = int(kpis.get("clients_medium") or 0)
    kpi_anomaly = int(kpis.get("clients_with_anomaly") or 0)
    kpi_reimb = kpis.get("average_reimbursement_ratio")
    kpi_debt = kpis.get("average_debt")
    kpi_score = kpis.get("average_risk_score")
    kpi_total = int(kpis.get("total_clients") or 0)
    filter_rt = (active_filters or {}).get("risk_tier")
    filter_action = (active_filters or {}).get("recommended_action")

    if any(raw in combined for raw in ("risk_tier=", "cluster_name=", "is_anomaly=", "recommended_action=")):
        return False

    # Rule A: no high-risk clients
    if kpi_high == 0:
        _no_high_forbidden = ("profils critiques", "cas critiques", "priorité élevée", "urgence", "priorisation forte")
        if "risque élevé" in narrative:
            _allowed = ("aucun client à risque élevé", "absence de clients à risque élevé",
                        "aucun profil à risque élevé", "risque élevé n'est présent")
            if not any(p in narrative for p in _allowed):
                return False
        if any(t in narrative for t in _no_high_forbidden):
            return False

    # Rule B: no medium-risk clients
    if kpi_medium == 0:
        _no_medium_forbidden = ("zone de transition", "bascule vers le risque élevé",
                                "risque moyen vers le risque élevé")
        if any(t in narrative for t in _no_medium_forbidden):
            return False

    # Rule C: no anomalies
    if kpi_anomaly == 0:
        _no_anomaly_forbidden = ("anomalies à traiter", "croiser les anomalies",
                                 "anomalies détectées deviennent prioritaires",
                                 "signal atypique", "avec anomalie",
                                 "anomalies présentes", "profils combinant risque et anomalie",
                                 "anomalie à croiser")
        if any(t in narrative for t in _no_anomaly_forbidden):
            return False
        if "anomalie" in narrative:
            allowed_anomaly = (
                "aucune anomalie",
                "sans anomalie",
                "absence d'anomalie",
                "absence de signal d'anomalie",
            )
            if not any(t in narrative for t in allowed_anomaly):
                return False

    # Rule D: very high reimbursement
    if kpi_reimb is not None and float(kpi_reimb) >= 0.95:
        if any(t in narrative for t in ("faible remboursement", "remboursement dégradé",
                                       "comportement de remboursement faible", "retard de remboursement")):
            return False

    # Rule E: zero debt
    if kpi_debt is not None and float(kpi_debt) == 0:
        if any(t in narrative for t in ("encours actif", "exposition financière",
                                       "dette active", "montant à recouvrer")):
            return False

    if filter_rt == "low" and any(t in narrative for t in ("urgence", "critique", "priorisation forte")):
        return False
    if filter_action == "monitor_only" and any(t in narrative for t in ("traitement prioritaire", "appel prioritaire", "urgence")):
        return False
    if kpi_total > 0 and kpi_high == kpi_total and kpi_score is not None and float(kpi_score) >= 0.70:
        if any(t in narrative for t in ("périmètre stable", "globalement stable", "suivi routine", "risque faible")):
            return False

    return True


def _global_profile_recommendations(kpis: dict[str, Any], active_filters: dict[str, Any]) -> list[str]:
    high = int(kpis.get("clients_high") or 0)
    medium = int(kpis.get("clients_medium") or 0)
    low = int(kpis.get("clients_low") or 0)
    anomaly = int(kpis.get("clients_with_anomaly") or 0)
    avg_debt = kpis.get("average_debt")
    avg_reimb = kpis.get("average_reimbursement_ratio")
    
    good_reimb = avg_reimb is not None and float(avg_reimb) >= 0.95
    weak_reimb = avg_reimb is not None and float(avg_reimb) < 0.75
    zero_debt = avg_debt is not None and float(avg_debt) == 0

    recs = []
    
    if high > 0:
        if weak_reimb and not zero_debt:
            recs.append(f"Clients à risque élevé : Prioriser les {high} clients à risque élevé, surtout ceux avec remboursement faible ou segment sensible.")
        else:
            recs.append(f"Clients à risque élevé : Traiter en priorité les {high} clients à risque élevé de ce périmètre.")
            
    if medium > 0:
        recs.append(f"Clients à risque moyen : Surveiller les {medium} clients à risque moyen afin d'éviter une dégradation.")
        
    if low > 0:
        recs.append(f"Clients à risque faible : Maintenir les {low} clients à risque faible en suivi routine.")
        
    if anomaly > 0:
        recs.append(f"Clients avec anomalie : Vérifier les {anomaly} anomalies comme signaux de tri, sans les considérer seules comme preuve de criticité.")
        
    dominant_segment_raw = str(kpis.get("dominant_segment") or "")
    dominant_segment = _SEGMENT_LABELS_FR.get(dominant_segment_raw, dominant_segment_raw)
    if dominant_segment:
        recs.append(f"Segment dominant : Comparer le segment {dominant_segment} aux segments dont le score moyen est plus élevé.")

    action_dominant = _ACTION_LABELS_FR.get(str(kpis.get("dominant_recommended_action") or ""), "")
    if action_dominant:
        recs.append(f"Action dominante : L'action dominante ({action_dominant}) doit orienter le type de suivi.")
        
    return recs


def _build_decision_support_from_kpis(kpis: dict[str, Any], active_filters: dict[str, Any]) -> list[dict[str, str]]:
    total = int(kpis.get("total_clients") or 0)
    high = int(kpis.get("clients_high") or 0)
    medium = int(kpis.get("clients_medium") or 0)
    low = int(kpis.get("clients_low") or 0)
    anomaly = int(kpis.get("clients_with_anomaly") or 0)
    avg_debt = kpis.get("average_debt")
    avg_reimb = kpis.get("average_reimbursement_ratio")
    risk_filter = active_filters.get("risk_tier")
    seg_filter = active_filters.get("cluster_name")
    anomaly_filter = active_filters.get("is_anomaly")
    action_filter = active_filters.get("recommended_action")
    search_filter = active_filters.get("search")
    dominant_segment_raw = str(kpis.get("dominant_segment") or "")
    dominant_segment = _SEGMENT_LABELS_FR.get(dominant_segment_raw, dominant_segment_raw) or "segment dominant"
    action_label = _ACTION_LABELS_FR.get(str(action_filter or kpis.get("dominant_recommended_action") or ""), "Suivi routine")
    seg_label = _SEGMENT_LABELS_FR.get(str(seg_filter), str(seg_filter)) if seg_filter else dominant_segment
    good_reimb = avg_reimb is not None and float(avg_reimb) >= 0.95
    zero_debt = avg_debt is not None and float(avg_debt) == 0

    def card(index: int, title: str, target: str, goal: str, focus: str) -> dict[str, str]:
        return {
            "priority": f"Priorité {index} — {title}",
            "target": target,
            "business_goal": goal,
            "recommended_focus": focus,
        }

    if total == 0:
        return [
            card(
                1,
                "Ajuster les filtres",
                "Aucun client trouvé",
                "Élargir le périmètre d'analyse",
                "Modifier les critères de recherche ou réinitialiser les filtres.",
            )
        ]

    if search_filter:
        return [
            card(1, "Vérifier les profils trouvés", f"{_fmt(total)} clients correspondant à la recherche", "Analyser un périmètre réduit", "Comparer les scores, segments et actions recommandées."),
            card(2, "Ouvrir le détail client", "Profils retournés", "Vérifier les signaux client", "Consulter la fiche client pour chaque profil pertinent."),
            card(3, "Générer le rapport client individuel", "Client sélectionné", "Obtenir une lecture détaillée", "Générer le rapport client si une analyse individuelle est nécessaire."),
        ]

    if seg_filter == "Bon-payeur" and anomaly_filter is False:
        return [
            card(1, "Maintenir le suivi standard", f"{_fmt(total)} clients Bon payeur", "Préserver la stabilité du segment", "Conserver un suivi routine."),
            card(2, "Segment de référence", "Segment Bon payeur", "Comparer les autres segments", "Utiliser ce groupe comme base de comparaison."),
            card(3, "Évolution périodique", "Prochains imports ML", "Détecter une éventuelle dégradation", "Suivre l'évolution du score."),
        ]

    if seg_filter == "Bon-payeur" and anomaly_filter is True:
        sms_target = f"{_fmt(total)} clients du segment Bon payeur"
        if action_filter == "sms_retention_offer":
            sms_target = f"{_fmt(total)} clients avec SMS personnalisé"
        focus = "Maintenir un suivi léger."
        if good_reimb and zero_debt:
            focus = "Maintenir un suivi léger si le remboursement est satisfaisant et la dette moyenne est nulle."
        return [
            card(1, "Vérifier le signal d'anomalie", f"{_fmt(anomaly)} clients concernés", "Confirmer si le signal est ponctuel ou récurrent", focus),
            card(2, "Maintenir le suivi du segment Bon payeur", f"{_fmt(total)} clients du segment Bon payeur", "Préserver la stabilité du segment", "Suivre l'évolution du score lors des prochains imports ML."),
            card(3, "Utiliser le SMS personnalisé comme action légère", sms_target, "Garder un contact simple sans mobilisation lourde", "Utiliser le SMS comme suivi préventif, pas comme action prioritaire."),
        ]

    if seg_filter == "SUSPENDED" and anomaly_filter is False and high > 0:
        repayment_focus = "Concentrer le suivi sur les situations où le remboursement confirme le risque."
        if good_reimb:
            repayment_focus = "Vérifier que le remboursement satisfaisant reste cohérent avec le score."
        return [
            card(1, "Profils suspendus les plus exposés", f"{_fmt(high)} clients à risque élevé", "Réduire l'exposition au risque", "L'absence d'anomalie ne signifie pas absence de risque. Classer les profils selon score, remboursement et segment."),
            card(2, "Comportement de remboursement", "Profils à suivre dans le segment Suspendu", "Identifier les profils fragiles", repayment_focus),
            card(3, "Comparaison segmentaire", "Segment Suspendu", "Mesurer le poids du segment", "Comparer ce segment aux autres segments."),
        ]

    if risk_filter == "high":
        return [
            card(1, "Profils les plus exposés", f"{_fmt(total)} clients à risque élevé", "Réduire l'exposition au risque", "Classer les clients selon score, remboursement et segment."),
            card(2, "Segments représentés", dominant_segment, "Concentrer le suivi", "Comparer les segments pour identifier les concentrations de risque."),
            card(3, "Suivi comparatif", "Prochaines générations ML", "Mesurer l'évolution", "Vérifier si le volume à risque élevé augmente ou diminue."),
        ]

    if risk_filter == "medium":
        return [
            card(1, "Profils à surveiller", f"{_fmt(total)} clients à risque moyen", "Prévenir la dégradation", "Suivre les profils dont le score ou le remboursement évolue défavorablement."),
            card(2, "Évolution du score", "Clients à score en progression", "Anticiper une montée en risque", "Comparer les prochains imports ML."),
            card(3, "Segment dominant", dominant_segment, "Cibler la surveillance", "Comparer ce segment au reste du portefeuille."),
        ]

    if risk_filter == "low":
        return [
            card(1, "Maintenir le suivi standard", f"{_fmt(total)} clients à risque faible", "Maintenir la stabilité", "Conserver un suivi routine."),
            card(2, "Segment de référence", f"{dominant_segment} stable", "Comparer les autres groupes", "Utiliser ce périmètre comme base de comparaison."),
            card(3, "Surveillance périodique", "Prochaines mises à jour", "Détecter les évolutions défavorables", "Vérifier si certains profils quittent le risque faible."),
        ]

    if anomaly_filter is True:
        risk_target = f"{_fmt(high)} clients à risque élevé" if high > 0 else f"{_fmt(medium)} clients à risque moyen" if medium > 0 else f"{_fmt(low)} clients à risque faible"
        risk_focus = "Ne traiter prioritairement que les anomalies accompagnées d'autres signaux défavorables." if high > 0 else "Classer les anomalies selon le score et le remboursement sans parler d'urgence."
        return [
            card(1, "Vérifier le signal d'anomalie", f"{_fmt(anomaly)} clients avec anomalie", "Confirmer si le signal est ponctuel ou récurrent", "Croiser l'anomalie avec le score, le segment et le remboursement."),
            card(2, "Niveau de risque associé", risk_target, "Prioriser correctement", risk_focus),
            card(3, "Suivi dans le temps", "Prochains imports ML", "Confirmer la tendance", "Vérifier si l'anomalie se répète."),
        ]

    if anomaly_filter is False or anomaly == 0:
        return [
            card(1, "Lecture par score et remboursement", f"{_fmt(total)} clients sans anomalie", "Prioriser sans anomalie détectée", "Classer les profils selon le score, le remboursement et le segment."),
            card(2, "Segment dominant", dominant_segment, "Contextualiser le risque", "Comparer ce segment aux autres segments."),
            card(3, "Suivi périodique", "Prochains imports ML", "Détecter une évolution future", "Surveiller les changements de score."),
        ]

    if seg_filter == "DISCONNECTED":
        if high > 0:
            return [
                card(1, "Suivi prioritaire du segment", f"{_fmt(high)} clients à risque élevé", "Cibler les profils sensibles", "Classer les profils selon score, remboursement et segment."),
                card(2, "Comparaison des profils", f"{_fmt(total)} clients Déconnectés", "Organiser le suivi", "Comparer les profils du segment selon leur score."),
                card(3, "Évolution du segment", "Prochains imports ML", "Mesurer la tendance", "Vérifier si le risque du segment augmente ou diminue."),
            ]
        return [
            card(1, "Suivi ciblé du segment", f"{_fmt(total)} clients Déconnectés", "Surveiller sans dramatiser", "Suivre les scores et le remboursement."),
            card(2, "Comparaison segmentaire", "Segment Déconnecté", "Contextualiser le risque", "Comparer ce segment aux autres segments."),
            card(3, "Surveillance périodique", "Prochains imports ML", "Détecter les évolutions", "Vérifier si certains profils deviennent plus sensibles."),
        ]

    if seg_filter == "ON-HOLD":
        return [
            card(1, "Surveillance de transition", f"{_fmt(total)} clients En attente", "Suivre l'évolution future", "Observer les changements de score et de segment."),
            card(2, "Comparaison segmentaire", "Segment En attente", "Situer le périmètre", "Comparer ce segment aux autres segments."),
            card(3, "Prochaines mises à jour", "Prochains imports ML", "Confirmer la tendance", "Vérifier si ces clients basculent vers un autre niveau de risque."),
        ]

    if action_filter == "sms_retention_offer":
        return [
            card(1, "Suivi léger", f"{_fmt(total)} clients avec SMS personnalisé", "Accompagner les profils concernés", "Utiliser un message personnalisé sans avantage commercial."),
            card(2, "Surveillance du score", "Profils concernés", "Éviter la dégradation", "Suivre l'évolution du score et du remboursement."),
            card(3, "Ajustement périodique", "Prochains imports ML", "Adapter le suivi", "Vérifier si l'action reste adaptée au périmètre."),
        ]

    if action_filter == "call_center_priority":
        target = f"{_fmt(high)} clients à risque élevé" if high > 0 else f"{_fmt(total)} clients concernés"
        focus = "Organiser un contact ciblé selon le score, le remboursement et le segment." if high > 0 else "Vérifier les profils avant de mobiliser un contact ciblé."
        return [
            card(1, "Contact ciblé", target, "Organiser le suivi prioritaire", focus),
            card(2, "Priorisation interne", dominant_segment, "Cibler les ressources", "Comparer les segments représentés dans le périmètre."),
            card(3, "Suivi comparatif", "Prochains imports ML", "Mesurer l'évolution", "Vérifier si l'action reste justifiée."),
        ]

    if action_filter == "monitor_only":
        return [
            card(1, "Suivi standard", f"{_fmt(total)} clients en suivi routine", "Maintenir la surveillance", "Conserver une surveillance périodique sans dramatisation."),
            card(2, "Segment dominant", dominant_segment, "Contextualiser le périmètre", "Comparer le segment dominant aux autres segments."),
            card(3, "Évolution périodique", "Prochains imports ML", "Détecter les changements", "Vérifier si certains profils nécessitent une action différente."),
        ]

    high_focus = "Traiter d'abord les profils avec score élevé et segment sensible." if good_reimb else "Traiter d'abord les profils avec score élevé, remboursement faible ou segment sensible."
    return [
        card(1, "Traitement prioritaire", f"{_fmt(high)} clients à risque élevé", "Réduire l'exposition au risque", high_focus),
        card(2, "Surveillance renforcée", f"{_fmt(medium)} clients à risque moyen", "Prévenir la dégradation", "Suivre l'évolution du score et du remboursement."),
        card(3, "Suivi standard", f"{_fmt(low)} clients à risque faible", "Maintenir la stabilité", "Conserver un suivi routine."),
    ]


def _global_business_rationale(kpis: dict[str, Any], active_filters: dict[str, Any]) -> list[str]:
    total = int(kpis.get("total_clients") or 0)
    high = int(kpis.get("clients_high") or 0)
    medium = int(kpis.get("clients_medium") or 0)
    low = int(kpis.get("clients_low") or 0)
    anomaly = int(kpis.get("clients_with_anomaly") or 0)
    avg_debt = kpis.get("average_debt")
    avg_reimb = kpis.get("average_reimbursement_ratio")
    good_reimb = avg_reimb is not None and float(avg_reimb) >= 0.95
    zero_debt = avg_debt is not None and float(avg_debt) == 0
    risk_filter = active_filters.get("risk_tier")
    seg_filter = active_filters.get("cluster_name")
    anomaly_filter = active_filters.get("is_anomaly")
    search_filter = active_filters.get("search")

    if total == 0:
        return [
            "Aucun client ne correspond aux critères sélectionnés.",
            "Le groupe est vide et ne permet pas de prioriser une action métier.",
        ]
    if search_filter:
        return [
            "Ce rapport porte sur un périmètre réduit issu de la recherche client.",
            "Il ne représente pas une tendance globale du portefeuille.",
            "La bonne lecture consiste à vérifier les profils trouvés un par un.",
        ]
    if risk_filter == "high" and anomaly_filter is False:
        return [
            "Tous les clients du périmètre relèvent du niveau de risque élevé.",
            "L'absence d'anomalie ne signifie pas absence de risque.",
            "Le score, le remboursement et le profil client expliquent la priorité de suivi.",
        ]
    if risk_filter == "low" or (total > 0 and low == total):
        return [
            "Le niveau de risque est faible sur ce périmètre.",
            "L'action recommandée relève du suivi routine ou standard.",
            "Aucun signal prioritaire ne justifie une mobilisation forte.",
        ]
    if seg_filter == "Bon-payeur" and anomaly_filter is True:
        rationale = [
            "Le segment reste globalement stable.",
            "L'anomalie seule ne suffit pas à justifier un suivi prioritaire.",
        ]
        if zero_debt:
            rationale.append("La dette moyenne nulle renforce la lecture maîtrisée du groupe.")
        if good_reimb:
            rationale.append("Le remboursement satisfaisant confirme que le suivi doit rester proportionné.")
        return rationale
    if seg_filter == "Bon-payeur":
        rationale = [
            "Le segment Bon payeur constitue un groupe stable.",
            "Le suivi routine reste adapté à ce périmètre.",
        ]
        if zero_debt:
            rationale.append("La dette moyenne nulle confirme qu'aucune action financière immédiate n'est nécessaire.")
        if good_reimb:
            rationale.append("Le remboursement satisfaisant renforce la lecture maîtrisée.")
        return rationale
    if anomaly_filter is False:
        return [
            "Aucune anomalie détectée ne structure l'action métier.",
            "Le suivi doit donc reposer sur le score, le segment et le remboursement.",
            "L'absence d'anomalie simplifie la lecture sans annuler le niveau de risque.",
        ]
    if anomaly_filter is True:
        return [
            "L'anomalie est un signal de surveillance, pas une preuve automatique de criticité.",
            "Elle devient prioritaire seulement si elle s'ajoute à un score ou un segment plus risqué.",
            "Le suivi doit vérifier si le signal est ponctuel ou récurrent.",
        ]
    if high > 0:
        rationale = [
            "Le risque élevé concentre l'effort métier immédiat.",
            "Les clients à risque moyen doivent être surveillés pour éviter une dégradation.",
            "Les clients stables servent de base de comparaison.",
        ]
        if anomaly > 0:
            rationale.append("Les anomalies renforcent la priorité uniquement lorsqu'elles se combinent avec d'autres signaux.")
        return rationale
    if medium > 0:
        return [
            "Aucun client à risque élevé n'est présent dans ce périmètre.",
            "Les clients à risque moyen ne sont pas encore prioritaires, mais doivent être surveillés.",
            "Le suivi doit détecter les évolutions défavorables.",
        ]
    return [
        "Le groupe est stable.",
        "Le suivi routine est adapté au niveau de risque observé.",
        "Ce périmètre peut servir de base de comparaison.",
    ]


def _global_structured_business_recommendations(kpis: dict[str, Any], active_filters: dict[str, Any]) -> list[dict[str, str]]:
    high = int(kpis.get("clients_high") or 0)
    medium = int(kpis.get("clients_medium") or 0)
    anomaly = int(kpis.get("clients_with_anomaly") or 0)
    avg_debt = kpis.get("average_debt")
    avg_reimb = kpis.get("average_reimbursement_ratio")
    
    good_reimb = avg_reimb is not None and float(avg_reimb) >= 0.95
    zero_debt = avg_debt is not None and float(avg_debt) == 0

    risk_filter = active_filters.get("risk_tier")
    seg_filter = active_filters.get("cluster_name")
    anomaly_filter = active_filters.get("is_anomaly")
    action_filter = active_filters.get("recommended_action")
    search_filter = active_filters.get("search")

    recs = []

    def _risk_example(base: str) -> str:
        if good_reimb:
            return "Analyser d'abord les clients à risque élevé selon leur score, leur segment et leur historique de suivi."
        if zero_debt:
            return "Analyser d'abord les clients à risque élevé selon leur score et leur segment, sans action financière immédiate."
        return base

    if int(kpis.get("total_clients") or 0) == 0:
        return [
            {
                "title": "Réinitialiser ou élargir les filtres",
                "why": "Aucun client ne correspond aux critères actuels.",
                "example": "Retirer un filtre trop restrictif, comme anomalie ou segment.",
                "expected_impact": "Obtenir un périmètre exploitable pour l'analyse.",
            }
        ]

    if seg_filter == "Bon-payeur" and high == 0 and (good_reimb or zero_debt):
        if anomaly_filter is True:
            return [
                {
                    "title": "Vérifier le signal d'anomalie",
                    "why": "L'anomalie doit être confirmée dans un segment dont les indicateurs restent maîtrisés.",
                    "example": "Vérifier si l'anomalie est ponctuelle ou récurrente lors des prochains imports.",
                    "expected_impact": "Éviter une mobilisation trop lourde sur un périmètre stable.",
                },
                {
                    "title": "Maintenir un suivi périodique",
                    "why": "Aucun client à risque élevé n'est présent et le remboursement reste complet.",
                    "example": "Comparer l'évolution du score sans déclencher de suivi prioritaire.",
                    "expected_impact": "Préserver la stabilité du segment Bon payeur.",
                },
                {
                    "title": "Utiliser le SMS comme suivi préventif",
                    "why": "Le SMS personnalisé convient à un suivi léger sans action lourde.",
                    "example": "Envoyer un message de suivi simple si le contact client est utile.",
                    "expected_impact": "Maintenir le lien client sans dramatiser le signal.",
                },
            ]
        else:
            return [
                {
                    "title": "Maintenir le suivi de routine",
                    "why": "Le segment présente une stabilité confirmée par les indicateurs de score et de remboursement.",
                    "example": "Réévaluer la situation lors du prochain cycle d'analyse.",
                    "expected_impact": "Optimiser le temps métier en se concentrant sur les segments à risque.",
                },
                {
                    "title": "Utiliser comme base de référence",
                    "why": "La solidité de ce segment permet de l'utiliser comme point de comparaison pour le reste du portefeuille.",
                    "example": "Comparer le score moyen de ce groupe avec les segments plus exposés.",
                    "expected_impact": "Améliorer la lecture globale du risque du portefeuille.",
                },
            ]

    if search_filter:
        recs.append({
            "title": "Analyser les profils ciblés",
            "why": "La recherche isole des clients précis qui nécessitent une vérification individuelle.",
            "example": "Ouvrir le détail client ou générer un rapport client individuel pour comparer leur situation.",
            "expected_impact": "Comprendre l'historique de chaque client trouvé avant d'agir."
        })
        recs.append({
            "title": "Décider profil par profil",
            "why": "Le résultat de recherche ne représente pas une tendance globale du portefeuille.",
            "example": "Comparer le score, le segment et le remboursement de chaque profil trouvé avant de choisir l'action.",
            "expected_impact": "Éviter une décision trop générale sur un périmètre réduit."
        })
        return recs

    if action_filter == "monitor_only":
        recs.extend([
            {
                "title": "Maintenir une surveillance périodique",
                "why": "Le suivi routine est adapté lorsque l'action recommandée ne demande pas de contact prioritaire.",
                "example": "Revoir les scores, le segment et le remboursement lors du prochain cycle d'analyse.",
                "expected_impact": "Préserver la maîtrise du portefeuille sans mobiliser inutilement les équipes."
            },
            {
                "title": "Détecter les exceptions futures",
                "why": "Un périmètre en suivi routine peut servir de base de comparaison pour repérer une évolution inhabituelle.",
                "example": "Comparer les prochains scores avec ce périmètre pour identifier les profils qui changent de niveau.",
                "expected_impact": "Réagir tôt sans dramatiser les profils actuellement suivis."
            },
        ])
        return recs

    if action_filter == "sms_retention_offer":
        recs.extend([
            {
                "title": "Organiser un suivi léger par SMS",
                "why": "L'envoi de SMS personnalisés permet de maintenir le contact sans mobiliser un traitement lourd.",
                "example": "Envoyer un message personnalisé rappelant la situation et le canal de suivi adapté.",
                "expected_impact": "Améliorer le taux de retour sur des profils à suivre avec une action simple."
            },
            {
                "title": "Prioriser les réponses reçues",
                "why": "Les retours clients permettent d'identifier les profils qui nécessitent ensuite un suivi plus direct.",
                "example": "Classer les réponses selon le score, le segment et la régularité du remboursement.",
                "expected_impact": "Transformer le SMS en premier filtre opérationnel."
            },
        ])
        return recs

    if risk_filter == "high":
        recs.append({
            "title": "Prioriser le traitement métier",
            "why": "Ces clients concentrent le niveau de risque le plus important et nécessitent une action immédiate.",
            "example": _risk_example("Commencer par les clients dont le remboursement est le moins régulier ou dont le segment est Déconnecté ou Suspendu."),
            "expected_impact": "Concentrer l'effort métier sur les profils les plus exposés."
        })
        if action_filter == "call_center_priority":
            recs.append({
                "title": "Organiser l'appel prioritaire",
                "why": "Le contact direct est l'action la plus adaptée pour ce niveau de risque.",
                "example": "Planifier une campagne d'appels ciblée pour qualifier la situation et proposer le bon suivi.",
                "expected_impact": "Accélérer la régularisation et qualifier la situation du client."
            })
    elif risk_filter == "medium":
        medium_example = (
            "Créer une liste de suivi des clients à risque moyen présentant une anomalie ou une évolution du score."
            if good_reimb
            else "Créer une liste de suivi des clients à risque moyen présentant une anomalie ou une baisse de remboursement."
        )
        recs.append({
            "title": "Surveiller les clients à risque moyen",
            "why": "Ils ne sont pas prioritaires immédiatement, mais peuvent se dégrader si les signaux deviennent moins favorables.",
            "example": medium_example,
            "expected_impact": "Anticiper la dégradation avant qu'elle ne nécessite un traitement prioritaire."
        })
    elif risk_filter == "low":
        recs.append({
            "title": "Maintenir un suivi de routine",
            "why": "Ces clients présentent un profil stable sans signal de risque imminent.",
            "example": "Organiser une surveillance périodique sans mobiliser prioritairement les ressources opérationnelles.",
            "expected_impact": "Garder une base de comparaison fiable tout en optimisant le temps métier."
        })
    else:
        # Global or complex filters
        if high > 0:
            recs.append({
                "title": "Prioriser les clients à risque élevé",
                "why": "Ils représentent le premier niveau de traitement métier et concentrent les profils les plus exposés.",
                "example": _risk_example("Analyser d'abord les clients à risque élevé dont le remboursement est le moins régulier ou dont le segment est Déconnecté ou Suspendu."),
                "expected_impact": "Réduire le temps passé sur les profils peu prioritaires et concentrer l'effort sur les cas réellement exposés."
            })
        if medium > 0:
            recs.append({
                "title": "Surveiller les clients à risque moyen",
                "why": "Ils ne sont pas prioritaires immédiatement, mais peuvent se dégrader si les signaux deviennent moins favorables.",
                "example": "Créer une liste de suivi des clients à risque moyen avec baisse de remboursement ou changement de score.",
                "expected_impact": "Anticiper la dégradation avant qu'elle ne devienne prioritaire."
            })
        
        recs.append({
            "title": "Comparer les segments par score moyen",
            "why": "Le segment le plus volumineux n'est pas toujours le segment le plus risqué.",
            "example": "Comparer Standard, Déconnecté, Suspendu, Bon payeur et En attente selon leur score moyen plutôt que selon leur volume.",
            "expected_impact": "Orienter le pilotage vers les segments qui concentrent le risque réel."
        })

    if anomaly_filter is True or (not active_filters and anomaly > 0):
        example_text = "Isoler les clients ayant à la fois une anomalie et un score plus élevé."
        if not good_reimb:
            example_text = "Isoler les clients ayant à la fois une anomalie, un score élevé et un remboursement moins régulier."
            
        recs.append({
            "title": "Signal de surveillance (Anomalies)",
            "why": "L'anomalie est un signal de tri qui devient critique lorsqu'elle se combine à un risque effectif élevé.",
            "example": example_text,
            "expected_impact": "Améliorer le ciblage opérationnel en croisant les signaux atypiques."
        })
    elif anomaly_filter is False or (not active_filters and anomaly == 0):
        recs.append({
            "title": "Piloter selon les fondamentaux (score et segment)",
            "why": "Aucune anomalie n’est détectée dans ce périmètre, la priorisation repose donc sur le risque et le segment.",
            "example": "Classer les profils selon leur score et la régularité de leur remboursement.",
            "expected_impact": "Maintenir un suivi structuré à partir des indicateurs de base disponibles."
        })

    if seg_filter in ("SUSPENDED", "DISCONNECTED"):
        if high > 0:
            is_disconnected = seg_filter == "DISCONNECTED"
            segment_example = (
                "Prioriser les clients du segment dont le score est élevé et le remboursement moins régulier."
                if zero_debt
                else "Prioriser les clients du segment dont le score est élevé, le remboursement moins régulier et l'encours à suivre."
            )
            segment_impact = (
                "Concentrer le suivi sur les profils les plus exposés du segment."
                if zero_debt
                else (
                    "Mieux cibler le suivi des profils déconnectés les plus exposés."
                    if is_disconnected
                    else "Réduire l'exposition sur les profils suspendus les plus sensibles."
                )
            )
            recs.append({
                "title": "Cibler l'action sur le segment Déconnecté" if is_disconnected else "Cibler l'action sur le segment Suspendu",
                "why": "Ces profils nécessitent un suivi prioritaire lorsque le segment se combine avec un niveau de risque élevé.",
                "example": segment_example,
                "expected_impact": segment_impact
            })
        else:
            recs.append({
                "title": "Surveiller le segment de façon ciblée",
                "why": "L'inactivité nécessite une vigilance, même si le niveau de risque immédiat n'est pas critique.",
                "example": "Surveiller l'évolution de la dette et du remboursement sur ces profils inactifs.",
                "expected_impact": "Maintenir la lisibilité du portefeuille inactif sans dramatisation."
            })

    if seg_filter == "Bon-payeur" and good_reimb and zero_debt:
        recs.append({
            "title": "Maintenir la stabilité du segment",
            "why": "Les indicateurs de dette et de remboursement confirment la solidité de ce groupe.",
            "example": "Ne pas prévoir d'action prioritaire et se limiter à la détection d'exceptions futures.",
            "expected_impact": "Optimiser le temps des équipes en évitant des actions inutiles sur les bons profils."
        })

    # Return top 4 unique recommendations by title
    seen = set()
    final_recs = []
    for rec in recs:
        title = rec["title"].casefold()
        if title not in seen:
            seen.add(title)
            final_recs.append(rec)
            if len(final_recs) == 4:
                break
    
    # Ensure at least 2 if total_clients > 0
    if len(final_recs) < 2 and int(kpis.get("total_clients") or 0) > 0:
        generic = {
            "title": "Suivi des évolutions",
            "why": "Il est essentiel de comparer l'évolution de ce périmètre lors des prochains cycles.",
            "example": "Comparer le score et le remboursement lors du prochain import de données.",
            "expected_impact": "Détecter les changements de tendance le plus tôt possible."
        }
        if generic["title"].casefold() not in seen:
            final_recs.append(generic)

    return final_recs


def _ensure_global_decision_sections(report: dict[str, Any], kpis: dict[str, Any], active_filters: dict[str, Any], decision_context: dict[str, Any]) -> dict[str, Any]:
    total = int(kpis.get("total_clients") or 0)
    high = int(kpis.get("clients_high") or 0)
    avg_debt = kpis.get("average_debt")
    avg_reimb = kpis.get("average_reimbursement_ratio")
    stable_bon_payeur_anomaly = (
        active_filters.get("cluster_name") == "Bon-payeur"
        and active_filters.get("is_anomaly") is True
        and high == 0
        and avg_debt is not None
        and float(avg_debt) == 0
        and avg_reimb is not None
        and float(avg_reimb) >= 0.95
    )
    report["report_title"] = _global_report_title(active_filters, total)
    
    # Force the deterministic decision support from Python
    report["decision_support"] = decision_context.get("decision_support_base") or []
    
    # For filtered reports, we apply "Python-first": structured sections are strictly deterministic.
    # Qwen only provides the narrative (summary and risk reading).
    if active_filters:
        report["business_recommendations"] = _global_structured_business_recommendations(kpis, active_filters)
        report["profile_recommendations"] = _global_profile_recommendations(kpis, active_filters)
        report["business_rationale"] = _global_business_rationale(kpis, active_filters)
        # Use main_findings from fallback for filtered reports to ensure 100% accuracy
        fallback = _fallback_global_report_final(kpis, active_filters, decision_context)
        report["main_findings"] = fallback.get("main_findings") or []

    if total == 0:
        report["executive_summary"] = "Aucun client ne correspond aux critères sélectionnés. Les filtres doivent être ajustés pour obtenir un périmètre exploitable."
        report["business_recommendations"] = _global_structured_business_recommendations(kpis, active_filters)
    elif stable_bon_payeur_anomaly:
        report["executive_summary"] = (
            "Ce périmètre regroupe des clients Bon payeur avec anomalie détectée. "
            "Les indicateurs restent maîtrisés : aucun client à risque élevé, dette moyenne nulle et remboursement complet. "
            "L'anomalie doit être vérifiée comme un signal atypique, sans traitement prioritaire."
        )
        report["business_recommendations"] = _global_structured_business_recommendations(kpis, active_filters)
    
    # Fallback for empty sections if still missing
    if not report.get("profile_recommendations"):
        report["profile_recommendations"] = _global_profile_recommendations(kpis, active_filters)
    if not report.get("business_rationale"):
        report["business_rationale"] = _global_business_rationale(kpis, active_filters)
    
    # Final safety control for recommendations
    report["business_recommendations"] = _controlled_global_business_recommendations(report, kpis, active_filters)
    return report


def _section_has_forbidden_terms(value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=False, default=str).lower()
    return (
        any(_contains_forbidden_term(text, term) for term in _GLOBAL_TECHNICAL_FORBIDDEN)
        or any(term in text for term in _GLOBAL_BUSINESS_FORBIDDEN)
        or any(phrase in text for phrase in _PHRASES_FORBIDDEN_GLOBAL)
    )


def _decision_support_validation_errors(decision_support: Any, kpis: dict[str, Any], active_filters: dict[str, Any] | None = None, decision_context: dict[str, Any] | None = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(decision_support, list) or not (1 <= len(decision_support) <= 4):
        return ["invalid_decision_support_count"]
    for index, item in enumerate(decision_support, start=1):
        if not isinstance(item, dict):
            errors.append(f"invalid_decision_support:{index}")
            continue
        for field in ("priority", "target", "business_goal", "recommended_focus"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                errors.append(f"invalid_decision_support:{index}:{field}")

    text = json.dumps(decision_support, ensure_ascii=False, default=str).lower()
    for term in _DECISION_SUPPORT_RAW_FORBIDDEN:
        if term in text:
            errors.append(f"decision_support_technical_label:{term}")
    for term in ("high", "medium", "low", "true", "false"):
        if re.search(rf"\b{term}\b", text):
            errors.append(f"decision_support_technical_label:{term}")

    high = int(kpis.get("clients_high") or 0)
    medium = int(kpis.get("clients_medium") or 0)
    low = int(kpis.get("clients_low") or 0)
    anomaly = int(kpis.get("clients_with_anomaly") or 0)
    avg_reimb = kpis.get("average_reimbursement_ratio")
    avg_debt = kpis.get("average_debt")
    search_filter = (active_filters or {}).get("search")
    anomaly_filter = (active_filters or {}).get("is_anomaly")

    if high == 0 and re.search(r"\b[1-9]\d*\s+clients?\s+à\s+risque\s+élev", text):
        errors.append("decision_support_contradiction:clients_high=0")
    if medium == 0 and re.search(r"\b[1-9]\d*\s+clients?\s+à\s+risque\s+moyen", text):
        errors.append("decision_support_contradiction:clients_medium=0")
    if low == 0 and re.search(r"\b[1-9]\d*\s+clients?\s+à\s+risque\s+faible", text):
        errors.append("decision_support_contradiction:clients_low=0")
    if anomaly == 0 and any(term in text for term in ("signal atypique", "anomalie à croiser", "profils avec anomalie", "anomalies présentes")):
        errors.append("decision_support_contradiction:clients_with_anomaly=0")
    if anomaly_filter is False and any(term in text for term in ("signal atypique", "anomalie à croiser", "profils avec anomalie", "anomalies présentes")):
        errors.append("decision_support_contradiction:is_anomaly=false")
    if high == 0 and any(term in text for term in ("traitement prioritaire", "profils les plus exposés", "urgence", "crise")):
        errors.append("decision_support_contradiction:priority_without_high")
    if avg_reimb is not None and float(avg_reimb) >= 0.95 and any(term in text for term in ("remboursement faible", "faible remboursement", "remboursement dégradé", "remboursement moins régulier")):
        errors.append("decision_support_contradiction:average_reimbursement_ratio>=95")
    if avg_debt is not None and float(avg_debt) == 0 and any(term in text for term in ("dette active", "encours actif", "exposition financière", "montant à recouvrer")):
        errors.append("decision_support_contradiction:average_debt=0")
    if search_filter and any(term in text for term in ("tendance globale", "portefeuille global", "segment dominant")):
        errors.append("decision_support_contradiction:search_global")
        
    # Strictly enforce Python's deterministic decision support base
    if decision_context and "decision_support_base" in decision_context:
        expected = decision_context["decision_support_base"]
        if len(decision_support) != len(expected):
            errors.append("decision_support_mismatch:count")
        else:
            for i, (gen, exp) in enumerate(zip(decision_support, expected)):
                # We check if the generated text is "compatible" with expected target/goal/priority
                # The LLM is allowed to rephrase but not to change the essence.
                # However, for 100% safety, we prefer strict matching or replacement.
                if gen.get("priority") != exp.get("priority"):
                    errors.append(f"decision_support_mismatch:{i}:priority")
    return errors


def _repair_global_report_sections(
    ai_narratives: dict[str, Any],
    kpis: dict[str, Any],
    active_filters: dict[str, Any],
    decision_context: dict[str, Any],
) -> dict[str, Any]:
    """
    Fusionne les narratifs IA (si valides) avec la structure déterministe Python.
    """
    # 1. Base déterministe complète (KPIs, Recs, Decision Support, etc.)
    final_report = _fallback_global_report_final(kpis, active_filters, decision_context)
    total = int(kpis.get("total_clients") or 0)
    if total == 0:
        final_report["executive_summary"] = _EMPTY_REPORT_SUMMARY
        final_report["internal_note"] = ""
        return final_report
    if not active_filters:
        high = int(kpis.get("clients_high") or 0)
        medium = int(kpis.get("clients_medium") or 0)
        final_report["executive_summary"] = (
            f"Le portefeuille compte {_fmt(total)} clients scorés, dont {_fmt(high)} à risque élevé "
            f"et {_fmt(medium)} à risque moyen. "
            "Le pilotage doit prioriser les profils les plus exposés, surveiller les clients à risque moyen "
            "et maintenir un suivi standard sur la base stable du portefeuille."
        )
    bon_payeur_medium_anomaly_stable = (
        active_filters.get("cluster_name") == "Bon-payeur"
        and active_filters.get("risk_tier") == "medium"
        and active_filters.get("is_anomaly") is True
        and float(kpis.get("average_debt") or 0) == 0
        and kpis.get("average_reimbursement_ratio") is not None
        and float(kpis.get("average_reimbursement_ratio") or 0) >= 0.95
    )
    if bon_payeur_medium_anomaly_stable:
        stable_text = (
            "Vérifier le signal d'anomalie sans déclencher de traitement prioritaire, "
            "car la dette moyenne est nulle et le remboursement est complet."
        )
        final_report["executive_summary"] = stable_text
        final_report["risk_reading"] = stable_text
        final_report["internal_note"] = stable_text
    
    # 2. Injection chirurgicale des narratifs IA seulement si présents
    if ai_narratives:
        # decision_summary -> executive_summary
        summary = ai_narratives.get("decision_summary")
        if active_filters and not bon_payeur_medium_anomaly_stable and summary and isinstance(summary, str) and summary.strip():
            final_report["executive_summary"] = summary.strip()
            
        # risk_reading
        risk = ai_narratives.get("risk_reading")
        if not bon_payeur_medium_anomaly_stable and risk and isinstance(risk, str) and risk.strip():
            final_report["risk_reading"] = risk.strip()
            
        # business_recommendations_narrative -> internal_note (invisible mais stocké) ou injecté en findings
        narrative_rec = ai_narratives.get("business_recommendations_narrative")
        if not bon_payeur_medium_anomaly_stable and narrative_rec and isinstance(narrative_rec, str) and narrative_rec.strip():
             final_report["internal_note"] = narrative_rec.strip()

    return final_report


def _controlled_global_business_recommendations(
    report: dict[str, Any],
    kpis: dict[str, Any],
    active_filters: dict[str, Any],
) -> list[dict[str, str]]:
    """Keep local model wording only when it produced complete structured cards."""
    raw_recs = report.get("business_recommendations") or []
    fallback = _global_structured_business_recommendations(kpis, active_filters)
    controlled: list[dict[str, str]] = []
    seen: set[str] = set()

    for item in raw_recs:
        if not isinstance(item, dict):
            continue
        rec = {
            "title": str(item.get("title") or "").strip(),
            "why": str(item.get("why") or "").strip(),
            "example": str(item.get("example") or "").strip(),
            "expected_impact": str(item.get("expected_impact") or "").strip(),
        }
        if not all(rec.values()):
            continue
        key = rec["title"].casefold()
        if key in seen:
            continue
        seen.add(key)
        controlled.append(rec)
        if len(controlled) == 4:
            break

    for rec in fallback:
        if len(controlled) >= 4:
            break
        key = rec["title"].casefold()
        if key in seen:
            continue
        seen.add(key)
        controlled.append(rec)

    return controlled[:4] or fallback[:4]


def _fallback_global_report_final(kpis: dict[str, Any], active_filters: dict[str, Any], decision_context: dict[str, Any]) -> dict[str, Any]:  # noqa: C901
    total = int(kpis.get("total_clients") or 0)
    high = int(kpis.get("clients_high") or 0)
    medium = int(kpis.get("clients_medium") or 0)
    low = int(kpis.get("clients_low") or 0)
    anomaly = int(kpis.get("clients_with_anomaly") or 0)
    avg_score = kpis.get("average_risk_score")
    avg_debt = kpis.get("average_debt")
    avg_reimb = kpis.get("average_reimbursement_ratio")
    dominant_seg_raw = kpis.get("dominant_segment") or ""
    dominant_action_raw = kpis.get("dominant_recommended_action") or "monitor_only"
    dominant_seg = _SEGMENT_LABELS_FR.get(dominant_seg_raw, dominant_seg_raw) or "Non défini"
    dominant_action = _ACTION_LABELS_FR.get(dominant_action_raw, "Suivi routine")

    risk_filter = active_filters.get("risk_tier")
    seg_filter = active_filters.get("cluster_name")
    anomaly_filter = active_filters.get("is_anomaly")
    action_filter = active_filters.get("recommended_action")
    search_filter = active_filters.get("search")
    seg_label = _SEGMENT_LABELS_FR.get(str(seg_filter), str(seg_filter)) if seg_filter else ""
    action_label = _ACTION_LABELS_FR.get(str(action_filter), str(action_filter)) if action_filter else dominant_action
    is_global = not active_filters

    score_val = float(avg_score) if avg_score is not None else None
    debt_val = float(avg_debt or 0)
    reimb_ratio = float(avg_reimb) if avg_reimb is not None else None
    reimb_pct = round(reimb_ratio * 100) if reimb_ratio is not None else None
    high_pct = round(high / total * 100) if total else 0
    medium_pct = round(medium / total * 100) if total else 0
    low_pct = round(low / total * 100) if total else 0

    has_high = high > 0
    has_medium = medium > 0
    has_anomaly = anomaly > 0
    all_low = total > 0 and low == total and not has_high and not has_medium
    zero_debt = debt_val == 0
    good_reimb = reimb_pct is not None and reimb_pct >= 95
    weak_reimb = reimb_pct is not None and reimb_pct < 75
    low_score = score_val is not None and score_val < 0.20
    moderate_score = score_val is not None and 0.20 <= score_val < 0.50
    high_score = score_val is not None and score_val >= 0.50
    stable = all_low or low_score

    def fmt_int(value: int) -> str:
        return _fmt(value)

    def score_text() -> str:
        if high_score:
            return "Le score moyen appelle une vigilance renforcée et une organisation claire du suivi métier."
        if moderate_score:
            return "Le score moyen traduit un risque global modéré, avec un suivi à concentrer sur les groupes les plus exposés."
        if low_score:
            return "Le score moyen confirme un périmètre maîtrisé, adapté à une surveillance standard."
        return "Le score moyen doit être interprété avec les autres signaux disponibles du périmètre."

    def reimbursement_text() -> str:
        if reimb_pct is None:
            return "Le remboursement moyen n'est pas disponible pour ce périmètre."
        if reimb_pct >= 95:
            return "Le remboursement moyen est satisfaisant et renforce la lecture stable du périmètre."
        if reimb_pct >= 75:
            return "Le remboursement moyen reste acceptable, avec un suivi ciblé sur les profils les moins réguliers."
        if zero_debt:
            return "Le remboursement moyen mérite un suivi métier, sans action financière immédiate sur ce périmètre."
        return "Le remboursement moyen constitue un signal à intégrer dans la priorisation du suivi."

    key_kpis = _global_key_kpis(kpis)

    if total == 0:
        return {
            "report_title": "Rapport de pilotage Bad Debts — Aucun résultat",
            "executive_summary": _EMPTY_REPORT_SUMMARY,
            "risk_reading": "Aucun signal de risque n'est disponible pour ce périmètre vide.",
            "key_kpis": key_kpis,
            "business_rationale": _global_business_rationale(kpis, active_filters),
            "decision_support": _build_decision_support_from_kpis(kpis, active_filters),
            "main_findings": ["Aucun client ne correspond aux critères sélectionnés."],
            "business_recommendations": _global_structured_business_recommendations(kpis, active_filters),
            "profile_recommendations": ["Recherche : Modifier les critères de recherche."],
            "decision_limits": "",
            "internal_note": "",
        }

    title = _global_report_title(active_filters, total)
    high_action_focus = (
        "Traiter d'abord les profils avec score élevé et segment sensible."
        if good_reimb
        else "Traiter d'abord les profils avec score élevé, remboursement faible ou segment sensible."
    )

    if is_global:
        if has_high:
            summary = (
                f"Le portefeuille compte {fmt_int(total)} clients scorés, dont {fmt_int(high)} à risque élevé "
                f"et {fmt_int(medium)} à risque moyen. "
                "Le pilotage doit prioriser les profils les plus exposés, surveiller les clients à risque moyen "
                "et maintenir un suivi standard sur la base stable du portefeuille."
            )
            risk_reading = (
                f"{score_text()} {reimbursement_text()} "
                f"Le segment dominant en volume est {dominant_seg}, mais le pilotage doit surtout comparer les segments selon leur score moyen."
            )
            decision_support = [
                {
                    "priority": "Priorité 1 — Traitement prioritaire",
                    "target": f"{fmt_int(high)} clients à risque élevé",
                    "business_goal": "Réduire l'exposition au risque",
                    "recommended_focus": f"Ces clients représentent {high_pct} % du portefeuille. {high_action_focus}",
                },
                {
                    "priority": "Priorité 2 — Surveillance renforcée",
                    "target": f"{fmt_int(medium)} clients à risque moyen" if has_medium else "Segments à surveiller",
                    "business_goal": "Prévenir la dégradation",
                    "recommended_focus": "Ces profils peuvent évoluer vers le risque élevé. Suivre l'évolution du score et du remboursement.",
                },
                {
                    "priority": "Priorité 3 — Suivi standard",
                    "target": f"{fmt_int(low)} clients à risque faible",
                    "business_goal": "Maintenir le suivi",
                    "recommended_focus": "Ces clients constituent la base stable du portefeuille. Conserver un suivi routine.",
                },
            ]
            findings = [
                f"{fmt_int(high)} clients relèvent du traitement prioritaire.",
                "Le segment dominant en volume ne doit pas être confondu avec le segment le plus exposé.",
                "La lecture par niveau de risque permet d'organiser les ressources métier.",
            ]
            if has_anomaly:
                findings.append(f"{fmt_int(anomaly)} anomalies doivent servir de signal complémentaire de tri.")
            if has_medium:
                findings.append(f"{fmt_int(medium)} profils intermédiaires constituent une zone de surveillance utile.")
            recommendations = [
                "Segmenter le pilotage en trois niveaux : traitement prioritaire, surveillance renforcée, suivi standard.",
                "Comparer les segments selon leur score moyen plutôt que selon leur volume seul.",
                "Concentrer les efforts métier sur les combinaisons de signaux les plus défavorables.",
            ]
            if has_anomaly:
                recommendations.append("Comparer les anomalies avec le score et le remboursement pour mieux cibler le suivi.")
        else:
            summary = (
                f"Le portefeuille compte {fmt_int(total)} clients scorés, dont {fmt_int(high)} à risque élevé "
                f"et {fmt_int(medium)} à risque moyen. "
                "Le pilotage doit prioriser les profils les plus exposés, surveiller les clients à risque moyen "
                "et maintenir un suivi standard sur la base stable du portefeuille."
            )
            risk_reading = (
                f"{score_text()} {reimbursement_text()} "
                + (
                    "Les profils intermédiaires constituent le principal axe de surveillance."
                    if has_medium
                    else "Le portefeuille est composé de profils maîtrisés, adaptés à un suivi de routine."
                )
            )
            decision_support = [
                {
                    "priority": "Priorité 1",
                    "target": "Suivi standard" if not has_medium else "Profils intermédiaires",
                    "business_goal": "Maintenir la maîtrise",
                    "recommended_focus": "Organiser un suivi périodique proportionné au niveau de risque observé.",
                },
                {
                    "priority": "Priorité 2",
                    "target": "Segments de référence",
                    "business_goal": "Comparer les évolutions",
                    "recommended_focus": "Utiliser les segments stables comme base de comparaison pour les prochains cycles d'analyse.",
                },
                {
                    "priority": "Priorité 3",
                    "target": "Portefeuille stable",
                    "business_goal": "Préserver la qualité du suivi",
                    "recommended_focus": "Maintenir une surveillance de routine sans mobilisation prioritaire des ressources métier.",
                },
            ]
            findings = [
                "Aucun client à risque élevé n'est présent dans ce périmètre.",
                "La stabilité globale permet de privilégier un suivi proportionné.",
                "Le segment dominant sert de repère pour comparer les évolutions futures.",
            ]
            if has_medium:
                findings.append("Les profils intermédiaires constituent le principal point de surveillance.")
            recommendations = [
                "Maintenir un suivi standard du portefeuille.",
                "Surveiller les évolutions des profils intermédiaires lorsqu'ils existent.",
                "Utiliser ce périmètre comme base comparative pour les analyses filtrées.",
            ]

    elif risk_filter == "high":
        if anomaly_filter is False or not has_anomaly:
            summary = (
                "Ce périmètre représente une zone prioritaire du pilotage métier. "
                "Même sans anomalie détectée, les clients présentent un niveau de risque élevé, porté par le score, le remboursement et le profil client. "
                f"L'action dominante « {action_label} » confirme la nécessité d'un suivi prioritaire."
            )
            risk_reading = (
                "L'absence d'anomalie simplifie la lecture, mais ne réduit pas la priorité du périmètre. "
                "Le risque est principalement porté par le score et le comportement de remboursement. "
                "Le suivi doit donc se concentrer sur les profils les plus exposés."
            )
            decision_support = [
                {
                    "priority": "Priorité 1",
                    "target": "Profils à risque élevé sans anomalie",
                    "business_goal": "Traiter les profils les plus exposés",
                    "recommended_focus": "Classer les clients selon le score, le remboursement et le segment afin de prioriser les cas les plus sensibles.",
                },
                {
                    "priority": "Priorité 2",
                    "target": "Remboursement moins régulier",
                    "business_goal": "Cibler les profils fragiles",
                    "recommended_focus": "Isoler les clients dont le remboursement est le moins régulier afin d'orienter le suivi métier.",
                },
                {
                    "priority": "Priorité 3",
                    "target": "Comparaison segmentaire",
                    "business_goal": "Affiner le pilotage",
                    "recommended_focus": "Comparer les segments représentés pour identifier les concentrations de risque.",
                },
            ]
            findings = [
                "Le périmètre reste prioritaire même sans anomalie détectée.",
                "Le score et le remboursement expliquent l'essentiel du niveau de suivi attendu.",
                "Les segments représentés doivent être comparés pour mieux organiser les priorités.",
            ]
            recommendations = [
                "Classer les profils selon le score, le segment et le remboursement.",
                "Organiser le suivi prioritaire sans utiliser l'anomalie comme axe de tri.",
                f"Appliquer l'action « {action_label} » aux profils les plus exposés du périmètre.",
            ]
        else:
            summary = (
                "Ce périmètre représente la zone prioritaire du pilotage métier. "
                "Les profils qui combinent ce niveau de risque avec un remboursement moins régulier doivent concentrer l'attention. "
                f"L'action dominante est « {action_label} »."
            )
            risk_reading = (
                f"{score_text()} {reimbursement_text()} "
                "Le suivi doit distinguer les profils les plus exposés et les segments qui concentrent le plus de risque."
            )
            decision_support = [
                {
                    "priority": "Priorité 1",
                    "target": "Profils les plus exposés",
                    "business_goal": "Réduire l'exposition au risque",
                    "recommended_focus": "Traiter d'abord les profils où le score élevé se combine avec une anomalie, un remboursement moins régulier ou un segment sensible.",
                },
                {
                    "priority": "Priorité 2",
                    "target": "Segments les plus représentés",
                    "business_goal": "Orienter les ressources métier",
                    "recommended_focus": "Comparer les segments présents pour repérer où concentrer le suivi.",
                },
                {
                    "priority": "Priorité 3",
                    "target": "Suivi comparatif",
                    "business_goal": "Mesurer l'évolution",
                    "recommended_focus": "Comparer ce périmètre aux prochaines générations de scoring afin de confirmer les priorités de suivi.",
                },
            ]
            findings = [
                "Ce périmètre concentre l'effort de pilotage le plus immédiat.",
                "Les anomalies renforcent la priorité lorsqu'elles se combinent avec le score.",
                "L'action dominante doit être appliquée selon le niveau d'exposition des profils.",
            ]
            recommendations = [
                "Classer les profils selon la combinaison score, segment et remboursement.",
                "Comparer les segments représentés pour orienter le suivi opérationnel.",
                f"Appliquer l'action « {action_label} » en priorité aux profils les plus exposés du périmètre.",
            ]
            if weak_reimb and not zero_debt:
                recommendations.append("Renforcer le suivi des profils dont le remboursement est le moins régulier.")

    elif risk_filter == "medium":
        if seg_filter == "Bon-payeur" and has_anomaly and zero_debt and good_reimb:
            summary = (
                "Ce périmètre regroupe des clients Bon payeur à risque moyen avec anomalie détectée. "
                "Vérifier le signal d'anomalie sans déclencher de traitement prioritaire, car la dette moyenne est nulle et le remboursement est complet."
            )
        else:
            summary = (
                "Ce périmètre correspond à une population de surveillance renforcée, sans lecture de crise. "
                "L'objectif métier est d'éviter une dégradation vers un niveau de risque supérieur en détectant les profils qui se fragilisent."
            )
        risk_reading = (
            f"{score_text()} {reimbursement_text()} "
            "Ces clients ne sont pas encore prioritaires, mais ils doivent être surveillés pour éviter une dégradation."
        )
        decision_support = [
            {
                "priority": "Priorité 1",
                "target": "Profils moyens avec anomalie" if has_anomaly else "Profils moyens à suivre",
                "business_goal": "Prévenir la dégradation",
                "recommended_focus": (
                    "Vérifier le signal d'anomalie sans déclencher de traitement prioritaire, car la dette moyenne est nulle et le remboursement est complet."
                    if seg_filter == "Bon-payeur" and has_anomaly and zero_debt and good_reimb
                    else "Surveiller les profils dont les signaux évoluent défavorablement afin d'agir avant une montée en risque."
                ),
            },
            {
                "priority": "Priorité 2",
                "target": "Remboursement moins régulier" if weak_reimb else "Segments représentés",
                "business_goal": "Cibler la surveillance",
                "recommended_focus": "Repérer les groupes où le suivi renforcé apporte le plus de valeur métier.",
            },
            {
                "priority": "Priorité 3",
                "target": "Évolution du score",
                "business_goal": "Anticiper la tendance",
                "recommended_focus": "Suivre l'évolution du score pour distinguer une situation ponctuelle d'une dégradation durable.",
            },
        ]
        findings = [
            "Le risque moyen représente une zone intermédiaire à surveiller.",
            "La prévention repose sur la détection des signaux qui se dégradent progressivement.",
            "Le suivi par segment permet de mieux cibler les efforts métier.",
        ]
        if has_anomaly:
            findings.insert(1, "Les anomalies doivent être lues comme des signaux de surveillance, pas comme une preuve automatique de criticité.")
        recommendations = [
            "Planifier un suivi renforcé des profils qui se dégradent.",
            "Comparer ce périmètre au portefeuille global pour mesurer son évolution.",
            "Différencier les actions selon les segments représentés.",
        ]

    elif (risk_filter == "low" or all_low or (seg_filter == "Bon-payeur" and stable)) and anomaly_filter is not True:
        summary = (
            f"Ce rapport porte sur le segment {seg_label}. " if seg_filter else "Ce périmètre présente une structure globalement stable. "
        )
        summary += (
            "Les indicateurs confirment un suivi standard, avec un profil maîtrisé et adapté à une surveillance de routine. "
            + ("Le remboursement satisfaisant renforce cette lecture. " if good_reimb else "")
            + f"L'action dominante est « {action_label} »."
        )
        risk_reading = (
            f"{score_text()} {reimbursement_text()} "
            "Ce périmètre constitue une base de référence utile pour comparer les segments ou groupes plus exposés."
        )
        decision_support = [
            {
                "priority": "Priorité 1",
                "target": "Suivi standard",
                "business_goal": "Maintenir le suivi routine",
                "recommended_focus": "Conserver une surveillance périodique sans mobiliser prioritairement les ressources métier.",
            },
            {
                "priority": "Priorité 2",
                "target": "Référence comparative",
                "business_goal": "Comparer les segments",
                "recommended_focus": "Utiliser ce périmètre comme base de comparaison pour interpréter les groupes plus exposés.",
            },
            {
                "priority": "Priorité 3",
                "target": "Évolution périodique",
                "business_goal": "Préserver la stabilité",
                "recommended_focus": "Suivre l'évolution future pour repérer les exceptions éventuelles sans dramatiser le périmètre.",
            },
        ]
        findings = [
            "Le périmètre est stable et se prête à une surveillance de routine.",
            "Ce groupe constitue une référence utile pour comparer les autres segments.",
            "L'action dominante confirme une logique de suivi standard.",
        ]
        if has_anomaly:
            findings.insert(1, "Les anomalies présentes restent atypiques dans ce périmètre stable et doivent être suivies de façon périodique.")
        recommendations = [
            "Maintenir le suivi de routine.",
            "Utiliser ce périmètre comme référence comparative.",
            "Suivre les exceptions éventuelles lors des prochains cycles d'analyse.",
        ]

    elif anomaly_filter is True:
        if seg_filter == "Bon-payeur" and not has_high and zero_debt and good_reimb:
            summary = (
                "Ce périmètre regroupe des clients Bon payeur avec anomalie détectée. "
                "Les indicateurs restent maîtrisés : aucun profil à risque élevé, dette moyenne nulle et remboursement complet. "
                "L'anomalie doit être vérifiée comme un signal atypique, en conservant un suivi de routine."
            )
        else:
            summary = (
                (f"Ce périmètre regroupe des clients du segment {seg_label} avec anomalie détectée. " if seg_filter else "Ce périmètre regroupe des clients avec anomalie détectée. ")
                + ("La priorité métier porte sur les profils où ce signal se combine avec un risque élevé ou un remboursement moins régulier. " if has_high or weak_reimb else "Le signal doit être interprété avec prudence, surtout lorsque les autres indicateurs restent maîtrisés. ")
                + f"L'action dominante est « {action_label} »."
            )
        risk_reading = (
            f"{score_text()} {reimbursement_text()} "
            "L'anomalie est un signal de tri, pas une conclusion à elle seule ; sa valeur dépend de sa combinaison avec le score, le segment et le remboursement."
        )
        decision_support = [
            {
                "priority": "Priorité 1",
                "target": "Anomalie avec risque confirmé" if has_high else "Anomalies à surveiller",
                "business_goal": "Cibler les signaux les plus utiles",
                "recommended_focus": (
                    "Analyser d'abord les profils où l'anomalie s'accompagne d'un score plus élevé ou d'un segment plus exposé."
                    if good_reimb
                    else "Analyser d'abord les profils où l'anomalie s'accompagne d'un score plus élevé ou d'un remboursement moins régulier."
                ),
            },
            {
                "priority": "Priorité 2",
                "target": "Segments concernés",
                "business_goal": "Contextualiser le signal",
                "recommended_focus": "Comparer les segments concernés pour distinguer un signal isolé d'une tendance de groupe.",
            },
            {
                "priority": "Priorité 3",
                "target": "Suivi périodique",
                "business_goal": "Confirmer la tendance",
                "recommended_focus": "Observer l'évolution du signal pour déterminer s'il est ponctuel ou durable.",
            },
        ]
        if seg_filter == "Bon-payeur" and not has_high and zero_debt and good_reimb:
            findings = [
                "Le segment Bon payeur conserve des indicateurs maîtrisés malgré l'anomalie.",
                "L'anomalie doit être vérifiée comme un signal ponctuel ou récurrent.",
                "Le SMS personnalisé reste une action légère et préventive.",
            ]
            recommendations = [
                "Vérifier si l'anomalie est ponctuelle ou récurrente.",
                "Maintenir un suivi périodique du segment Bon payeur.",
                "Utiliser le SMS comme suivi préventif standard.",
            ]
        else:
            findings = [
                "L'anomalie doit être lue comme un signal de priorisation, pas comme une conclusion isolée.",
                "Les profils cumulant plusieurs signaux défavorables méritent l'attention la plus forte.",
                "Le segment dominant aide à contextualiser la nature du signal.",
            ]
            recommendations = [
                "Croiser l'anomalie avec le score, le segment et le remboursement.",
                "Distinguer les signaux ponctuels des tendances qui se répètent.",
                "Orienter le suivi vers les profils cumulant plusieurs signaux défavorables.",
            ]

    elif seg_filter and anomaly_filter is False:
        if seg_filter == "SUSPENDED" and has_high:
            summary = (
                "Ce rapport met en évidence un périmètre Suspendu sans anomalie détectée, mais fortement exposé au risque. "
                f"L'absence d'anomalie ne réduit pas la priorité métier : le score moyen et l'action dominante « {action_label} » indiquent un segment nécessitant un suivi prioritaire."
            )
            risk_reading = (
                f"{score_text()} {reimbursement_text()} "
                "Le risque est porté principalement par le score et le comportement de remboursement, et non par un signal d'anomalie. "
                "L'absence d'anomalie ne doit donc pas être interprétée comme une absence de risque."
            )
            decision_support = [
                {
                    "priority": "Priorité 1",
                    "target": "Profils Suspendus les plus exposés",
                    "business_goal": "Organiser le suivi prioritaire",
                    "recommended_focus": "Classer les profils Suspendus selon le score, le remboursement et le montant moyen afin de cibler le suivi métier.",
                },
                {
                    "priority": "Priorité 2",
                    "target": "Comportement de remboursement",
                    "business_goal": "Affiner la priorisation",
                    "recommended_focus": "Analyser les profils dont le remboursement est le moins régulier pour prioriser le traitement métier.",
                },
                {
                    "priority": "Priorité 3",
                    "target": "Comparaison segmentaire",
                    "business_goal": "Mesurer le poids du segment",
                    "recommended_focus": "Comparer le segment Suspendu aux autres segments pour mesurer son poids dans le risque global.",
                },
            ]
            findings = [
                "Le segment Suspendu peut rester prioritaire même sans anomalie détectée.",
                "L'absence d'anomalie simplifie la lecture sans annuler le niveau de risque.",
                "Le score et le remboursement structurent la priorisation du suivi.",
            ]
            recommendations = [
                "Organiser le suivi prioritaire du segment Suspendu selon le score, le remboursement et le montant moyen.",
                "Concentrer l'effort métier sur les profils Suspendus les plus exposés.",
                "Comparer ce segment aux autres segments pour mesurer son poids dans le risque global.",
            ]
        else:
            summary = (
                f"Ce rapport porte sur le segment {seg_label} sans anomalie détectée. "
                + ("La priorisation repose sur le score, le segment et le remboursement. " if has_high else "Le suivi doit rester proportionné aux signaux observés, sans dramatiser le segment. ")
                + f"L'action dominante est « {action_label} »."
            )
            risk_reading = (
                f"{score_text()} {reimbursement_text()} "
                "L'absence d'anomalie simplifie la lecture : le pilotage doit s'appuyer sur le niveau de risque effectif, le segment et le remboursement."
            )
            decision_support = [
                {
                    "priority": "Priorité 1",
                    "target": f"Score et segment {seg_label}",
                    "business_goal": "Cibler sans anomalie",
                    "recommended_focus": f"Analyser le segment {seg_label} selon le score et le niveau de risque effectif.",
                },
                {
                    "priority": "Priorité 2",
                    "target": "Remboursement",
                    "business_goal": "Affiner la surveillance",
                    "recommended_focus": "Comparer les profils selon leur comportement de remboursement pour ajuster le suivi.",
                },
                {
                    "priority": "Priorité 3",
                    "target": "Suivi périodique",
                    "business_goal": "Maintenir la lisibilité",
                    "recommended_focus": "Observer l'évolution du segment lors des prochains cycles d'analyse.",
                },
            ]
            findings = [
                f"Le segment {seg_label} sans anomalie nécessite une lecture fondée sur le score et le remboursement.",
                "L'absence d'anomalie rend le périmètre plus lisible.",
                "La comparaison avec les autres segments permet de mieux qualifier le suivi attendu.",
            ]
            recommendations = [
                f"Piloter le segment {seg_label} selon le score et le remboursement.",
                "Comparer ce périmètre avec les segments présentant des anomalies.",
                "Maintenir un suivi périodique adapté au niveau de risque effectif.",
            ]

    elif anomaly_filter is False:
        summary = (
            "Ce périmètre regroupe des clients sans anomalie détectée. "
            + ("La priorisation repose donc sur le score, le segment et le remboursement. " if has_high else "La lecture métier reste orientée vers un suivi standard ou ciblé selon le score. ")
            + f"L'action dominante est « {action_label} »."
        )
        risk_reading = (
            f"{score_text()} {reimbursement_text()} "
            "L'absence d'anomalie simplifie la lecture : le pilotage doit s'appuyer sur les indicateurs de risque effectif et la segmentation."
        )
        decision_support = [
            {
                "priority": "Priorité 1",
                "target": "Profils les plus exposés" if has_high else "Suivi selon le score",
                "business_goal": "Cibler sans anomalie",
                "recommended_focus": "Classer le périmètre selon le score, le segment et le remboursement, sans utiliser l'anomalie comme axe de tri.",
            },
            {
                "priority": "Priorité 2",
                "target": "Segments représentés",
                "business_goal": "Orienter le pilotage",
                "recommended_focus": "Comparer les segments présents pour comprendre où concentrer la surveillance.",
            },
            {
                "priority": "Priorité 3",
                "target": "Surveillance périodique",
                "business_goal": "Maintenir la lisibilité",
                "recommended_focus": "Suivre l'évolution du périmètre afin de détecter tout changement de profil.",
            },
        ]
        findings = [
            "L'absence d'anomalie rend le périmètre plus lisible.",
            "La segmentation et le score deviennent les principaux leviers de lecture.",
            "Le suivi périodique reste utile pour détecter les évolutions futures.",
        ]
        recommendations = [
            "Piloter ce périmètre selon le score et le segment.",
            "Comparer ce groupe avec le périmètre présentant des anomalies.",
            "Maintenir une surveillance périodique adaptée au niveau de risque réel.",
        ]

    elif seg_filter:
        summary = (
            f"Ce rapport porte sur le segment {seg_label}. "
            + ("Ce segment demande une vigilance ciblée, car il contient des profils fortement exposés. " if has_high else "Le suivi doit rester ciblé sur les signaux observés, sans dramatiser le segment. ")
            + f"L'action dominante est « {action_label} »."
        )
        risk_reading = (
            f"{score_text()} {reimbursement_text()} "
            "La lecture métier doit comparer ce segment au portefeuille global afin de distinguer un effet de volume d'un véritable signal de risque."
        )
        decision_support = [
            {
                "priority": "Priorité 1",
                "target": f"Profils exposés du segment {seg_label}" if has_high else f"Suivi ciblé du segment {seg_label}",
                "business_goal": "Adapter le pilotage au segment",
                "recommended_focus": "Analyser les profils du segment selon le score, le remboursement et l'action recommandée dominante.",
            },
            {
                "priority": "Priorité 2",
                "target": "Comparaison portefeuille",
                "business_goal": "Contextualiser le segment",
                "recommended_focus": "Comparer ce segment aux autres segments pour déterminer s'il concentre réellement plus de signaux défavorables.",
            },
            {
                "priority": "Priorité 3",
                "target": "Évolution du segment",
                "business_goal": "Suivre la tendance",
                "recommended_focus": "Observer l'évolution du segment dans le temps pour confirmer ou ajuster le niveau de suivi.",
            },
        ]
        findings = [
            f"Le segment {seg_label} nécessite une lecture dédiée plutôt qu'une lecture uniquement globale.",
            "Le volume du segment ne suffit pas à déterminer son niveau d'attention métier.",
            "La comparaison avec les autres segments permet de mieux qualifier le suivi attendu.",
        ]
        if has_high:
            findings.insert(1, "Les profils les plus exposés du segment concentrent l'effort de pilotage.")
        recommendations = [
            f"Piloter le segment {seg_label} selon le score, le remboursement et l'action dominante.",
            "Comparer le segment au portefeuille global.",
            "Suivre l'évolution du segment lors des prochains cycles d'analyse.",
        ]

    elif action_filter:
        action_focus = {
            "call_center_priority": "Le périmètre appelle un traitement prioritaire par le centre de relation client.",
            "sms_retention_offer": "Le périmètre appelle un suivi personnalisé par SMS, sans logique promotionnelle.",
            "monitor_only": "Le périmètre relève principalement du suivi routine et ne doit pas être dramatisé.",
        }.get(str(action_filter), "Le périmètre doit être lu selon l'action recommandée dominante.")
        summary = f"Ce rapport porte sur l'action « {action_label} ». {action_focus}"
        risk_reading = (
            f"{score_text()} {reimbursement_text()} "
            "L'action recommandée sert de regroupement opérationnel ; la priorité réelle dépend ensuite des signaux observés dans ce groupe."
        )
        decision_support = [
            {
                "priority": "Priorité 1",
                "target": action_label,
                "business_goal": "Aligner l'action et le niveau de suivi",
                "recommended_focus": "Appliquer l'action avec un niveau d'intensité adapté au score et au segment.",
            },
            {
                "priority": "Priorité 2",
                "target": "Groupes à surveiller" if has_high or has_medium else "Périmètre stable",
                "business_goal": "Affiner le pilotage",
                "recommended_focus": "Comparer les profils du groupe pour distinguer les situations de suivi standard des situations à surveiller davantage.",
            },
            {
                "priority": "Priorité 3",
                "target": "Évolution future",
                "business_goal": "Confirmer l'action",
                "recommended_focus": "Observer l'évolution des signaux pour confirmer la pertinence du regroupement opérationnel.",
            },
        ]
        findings = [
            f"L'action « {action_label} » regroupe un périmètre à piloter de façon homogène mais graduée.",
            "La lecture par score permet d'éviter une application uniforme de l'action.",
            "Le segment dominant aide à contextualiser le pilotage opérationnel.",
        ]
        recommendations = [
            f"Adapter l'intensité du suivi associé à « {action_label} » selon le score.",
            "Comparer les segments présents dans ce groupe d'action.",
            "Suivre l'évolution du périmètre pour confirmer le ciblage opérationnel.",
        ]

    else:
        summary = (
            f"Ce rapport porte sur le périmètre filtré. "
            + ("Il demande une vigilance renforcée, avec une attention portée aux groupes les plus exposés. " if has_high or high_score else "Il présente une lecture globalement maîtrisée, à piloter par suivi ciblé. ")
            + f"Le segment dominant est {dominant_seg} et l'action dominante est « {dominant_action} »."
        )
        risk_reading = (
            f"{score_text()} {reimbursement_text()} "
            "Le pilotage doit comparer les profils entre eux : le volume seul ne suffit pas à identifier les clients à suivre en premier."
        )
        decision_support = [
            {
                "priority": "Priorité 1",
                "target": "Profils les plus exposés" if has_high else "Groupes à surveiller",
                "business_goal": "Concentrer l'effort métier",
                "recommended_focus": "Identifier les profils où le score, le segment et le remboursement justifient un suivi plus attentif.",
            },
            {
                "priority": "Priorité 2",
                "target": "Segment dominant",
                "business_goal": "Contextualiser le volume",
                "recommended_focus": f"Comparer le segment {dominant_seg} aux autres segments du périmètre pour éviter une lecture uniquement volumétrique.",
            },
            {
                "priority": "Priorité 3",
                "target": "Suivi périodique",
                "business_goal": "Mesurer l'évolution",
                "recommended_focus": "Suivre l'évolution des indicateurs pour confirmer ou ajuster les priorités métier.",
            },
        ]
        findings = [
            "Le périmètre filtré permet de cibler un groupe précis du portefeuille.",
            "Le volume dominant ne doit pas être confondu avec le niveau de risque.",
            "La combinaison du score, du segment et du remboursement reste le meilleur axe de pilotage.",
        ]
        recommendations = [
            "Comparer le périmètre filtré au portefeuille global.",
            "Orienter les ressources vers les combinaisons de signaux les plus défavorables.",
            "Utiliser les filtres pour comparer les segments et les actions recommandées.",
        ]

    result = {
        "report_title": title,
        "executive_summary": summary,
        "risk_reading": risk_reading,
        "key_kpis": key_kpis,
        "business_rationale": _global_business_rationale(kpis, active_filters),
        "decision_support": decision_support[:4],
        "main_findings": findings[:5],
        "business_recommendations": _global_structured_business_recommendations(kpis, active_filters),
        "profile_recommendations": _global_profile_recommendations(kpis, active_filters),
        "decision_limits": "",
        "internal_note": "",
    }
    return result
