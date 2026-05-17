from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
import time
import io
from pathlib import Path
from typing import Any


# Configuration safe pour stdout/stderr sur Windows
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.services.bad_debts_llm_report_service import (  # noqa: E402
    _allowed_global_numbers,
    _generated_numbers_are_allowed,
    _global_report_title,
    _global_report_number_narrative,
    generate_global_llm_report,
)
from app.services.bad_debts_service import BadDebtsService  # noqa: E402


PAYLOADS: list[tuple[str, dict[str, Any]]] = [
    ("Aucun filtre", {}),
    ("Risque eleve", {"risk_tier": "high"}),
    ("Risque moyen", {"risk_tier": "medium"}),
    ("Risque faible", {"risk_tier": "low"}),
    ("Avec anomalie", {"is_anomaly": True}),
    ("Sans anomalie", {"is_anomaly": False}),
    ("Segment Standard", {"cluster_name": "Standard"}),
    ("Bon payeur sans anomalie", {"cluster_name": "Bon-payeur", "is_anomaly": False}),
    ("Bon payeur avec anomalie", {"cluster_name": "Bon-payeur", "is_anomaly": True}),
    ("Suspendu sans anomalie", {"cluster_name": "SUSPENDED", "is_anomaly": False}),
    ("Deconnecte", {"cluster_name": "DISCONNECTED"}),
    ("En attente", {"cluster_name": "ON-HOLD"}),
    ("Action appel prioritaire", {"recommended_action": "call_center_priority"}),
    ("Action SMS", {"recommended_action": "sms_retention_offer"}),
    ("Action suivi routine", {"recommended_action": "monitor_only"}),
    (
        "Risque eleve sans anomalie appel",
        {"risk_tier": "high", "is_anomaly": False, "recommended_action": "call_center_priority"},
    ),
    ("Risque moyen avec anomalie", {"risk_tier": "medium", "is_anomaly": True}),
    (
        "Suspendu sans anomalie appel",
        {"cluster_name": "SUSPENDED", "is_anomaly": False, "recommended_action": "call_center_priority"},
    ),
    (
        "Bon payeur sans anomalie routine",
        {"cluster_name": "Bon-payeur", "is_anomaly": False, "recommended_action": "monitor_only"},
    ),
    (
        "Bon payeur avec anomalie SMS",
        {"cluster_name": "Bon-payeur", "is_anomaly": True, "recommended_action": "sms_retention_offer"},
    ),
    ("Recherche inexistante", {"search": "000000000000000000"}),
    (
        "Medium Standard Anomaly SMS",
        {"risk_tier": "medium", "cluster_name": "Standard", "is_anomaly": True, "recommended_action": "sms_retention_offer"},
    ),
    (
        "High SUSPENDED NoAnomaly Call",
        {"risk_tier": "high", "cluster_name": "SUSPENDED", "is_anomaly": False, "recommended_action": "call_center_priority"},
    ),
    (
        "Low Bon-payeur NoAnomaly Monitor",
        {"risk_tier": "low", "cluster_name": "Bon-payeur", "is_anomaly": False, "recommended_action": "monitor_only"},
    ),
    ("DISCONNECTED NoAnomaly", {"cluster_name": "DISCONNECTED", "is_anomaly": False}),
    ("ON-HOLD Medium", {"cluster_name": "ON-HOLD", "risk_tier": "medium"}),
    ("Search 2169", {"search": "2169"}),
    ("Bon payeur risque moyen", {"risk_tier": "medium", "cluster_name": "Bon-payeur"}),
]

REQUIRED_REPORT_FIELDS = (
    "report_title",
    "executive_summary",
    "risk_reading",
    "business_rationale",
    "decision_support",
    "main_findings",
    "business_recommendations",
    "profile_recommendations",
)

TECHNICAL_FORBIDDEN = (
    "ollama",
    "openai",
    "gpt",
    "api",
    "fastapi",
    "postgresql",
    "backend",
    "frontend",
    "json",
    "payload",
    "run_id",
    "action_id",
    "agent_run_id",
)

WEAK_PHRASES = (
    "ne remplace pas",
    "utiliser uniquement",
    "ce rapport ne constitue pas",
    "doit être validé",
    "doit etre valide",
    "réexaminer le périmètre",
    "reexaminer le perimetre",
)

NO_ANOMALY_FORBIDDEN = (
    "anomalies présentes",
    "anomalies presentes",
    "anomalie à croiser",
    "anomalie a croiser",
    "signal atypique",
    "profils avec anomalie",
    "anomalie combinée",
    "anomalie combinee",
)

NO_HIGH_FORBIDDEN = (
    "profils les plus exposés",
    "profils les plus exposes",
    "cas critiques",
    "urgence",
    "priorité forte",
    "priorite forte",
)

LOW_RISK_FORBIDDEN = (
    "urgence",
    "critique",
    "traitement prioritaire",
    "vigilance renforcée",
    "vigilance renforcee",
)

GOOD_REIMBURSEMENT_FORBIDDEN = (
    "remboursement moins régulier",
    "remboursement moins regulier",
    "remboursement faible",
    "remboursement dégradé",
    "remboursement degrade",
    "faible remboursement",
)

ZERO_DEBT_FORBIDDEN = (
    "dette active",
    "encours actif",
    "exposition financière",
    "exposition financiere",
    "montant à recouvrer",
    "montant a recouvrer",
)

BON_PAYEUR_STABLE_FORBIDDEN = (
    "profils exposés",
    "profils exposes",
    "profils sensibles",
    "traitement prioritaire",
    "risque élevé",
    "risque eleve",
    "faible remboursement",
    "exposition financière",
    "exposition financiere",
)

BON_PAYEUR_ANOMALY_STABLE_FORBIDDEN = (
    "surveiller de près",
    "surveiller de pres",
    "profils exposés",
    "profils exposes",
    "profils sensibles",
    "remboursement faible",
    "dette active",
    "exposition financière",
    "exposition financiere",
)

EMPTY_RECOMMENDATION_FORBIDDEN = (
    "suivi routine",
    "risque élevé",
    "risque eleve",
    "risque moyen",
    "appel prioritaire",
    "sms personnalisé",
    "sms personnalise",
    "surveiller les clients",
    "prioriser les clients",
    "suivi standard",
    "clients à risque",
    "clients a risque",
    "anomalies à croiser",
    "anomalies a croiser",
)

SMS_FORBIDDEN = (
    "remise",
    "bonus",
    "réduction",
    "reduction",
    "cadeau",
    "offre commerciale",
)

SEARCH_GLOBAL_FORBIDDEN = (
    "portefeuille global",
    "tendance globale",
    "segment dominant",
)

DECISION_SUPPORT_RAW_FORBIDDEN = (
    "high",
    "medium",
    "low",
    "risk_tier",
    "effective_tier",
    "cluster_name",
    "recommended_action",
    "sms_retention_offer",
    "call_center_priority",
    "monitor_only",
    "true",
    "false",
)


def console_text(value: Any) -> str:
    """Normalise le texte pour l'affichage console Windows."""
    if value is None:
        return "-"
    if isinstance(value, (list, dict)):
        value = json.dumps(value, ensure_ascii=False)
    text = str(value)
    return (
        text
        .replace("\u202f", " ")
        .replace("\u00a0", " ")
    )


def safe_print(*args, **kwargs):
    """Affiche du texte de manière sécurisée contre les UnicodeEncodeError."""
    text = " ".join(str(arg) for arg in args)
    try:
        print(text, **kwargs)
    except UnicodeEncodeError:
        try:
            print(text.encode("utf-8", errors="replace").decode("utf-8", errors="replace"), **kwargs)
        except Exception:
            # Fallback ultime pour ne pas bloquer le script
            print("ERROR: Unicode display failed", file=sys.stderr)


def _report_text(report: dict[str, Any]) -> str:
    decision_text = []
    for item in report.get("decision_support") or []:
        if isinstance(item, dict):
            decision_text.extend(
                str(item.get(field) or "")
                for field in ("priority", "target", "business_goal", "recommended_focus")
            )
    recommendation_text = []
    for item in report.get("business_recommendations") or []:
        if isinstance(item, dict):
            recommendation_text.extend(
                str(item.get(field) or "")
                for field in ("title", "why", "example", "expected_impact")
            )
        else:
            recommendation_text.append(str(item))
    parts = [
        str(report.get("report_title") or ""),
        str(report.get("executive_summary") or ""),
        str(report.get("risk_reading") or ""),
        *[str(item) for item in report.get("business_rationale") or []],
        *[str(item) for item in report.get("main_findings") or []],
        *recommendation_text,
        *[str(item) for item in report.get("profile_recommendations") or []],
        *decision_text,
    ]
    return " ".join(part for part in parts if part).strip()


def _decision_support_text(report: dict[str, Any]) -> str:
    parts = []
    for item in report.get("decision_support") or []:
        if isinstance(item, dict):
            parts.extend(str(item.get(field) or "") for field in ("priority", "target", "business_goal", "recommended_focus"))
        else:
            parts.append(str(item))
    return " ".join(parts).strip()


def _validate_business_recommendations(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    recs = report.get("business_recommendations")
    if not isinstance(recs, list) or not recs:
        return ["business_recommendations invalide"]
    if len(recs) > 4:
        errors.append("business_recommendations trop longues")
    for index, item in enumerate(recs, start=1):
        if isinstance(item, str):
            if not item.strip():
                errors.append(f"business_recommendations[{index}] vide")
            continue
        if isinstance(item, dict):
            missing = [
                field
                for field in ("title", "why", "example", "expected_impact")
                if not isinstance(item.get(field), str) or not item.get(field).strip()
            ]
            if missing:
                errors.append(f"business_recommendations[{index}] structure incomplète: {','.join(missing)}")
            continue
        errors.append(f"business_recommendations[{index}] type invalide")
    if payload.get("cluster_name") == "Bon-payeur" and payload.get("risk_tier") == "medium":
        allowed_phrase = (
            "sans traitement prioritaire" in text_l
            or ("sans d" in text_l and "clencher de traitement prioritaire" in text_l)
            or "ne pas mobiliser un traitement prioritaire" in text_l
        )
        if allowed_phrase:
            errors = [
                error for error in errors
                if error not in {
                    "decision_support prioritaire alors que clients_high=0",
                    "contradiction Bon payeur stable: traitement prioritaire",
                    "contradiction Bon payeur anomalie stable: traitement prioritaire",
                }
            ]
        errors = [
            error for error in errors
            if error not in {
                "contradiction Bon payeur stable: risque Ã©levÃ©",
                "contradiction Bon payeur stable: risque eleve",
            }
        ]

    return errors


def _contains_any(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term in text]


def _contains_forbidden_term(text: str, term: str) -> bool:
    if term.isascii() and term.isalnum() and len(term) <= 4:
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text))
    return term in text


def _contains_forbidden_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if _contains_forbidden_term(text, term)]


def _validate_business_recommendations(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    recs = report.get("business_recommendations")
    if not isinstance(recs, list) or not recs:
        return ["business_recommendations invalide"]
    if len(recs) > 4:
        errors.append("business_recommendations trop longues")
    for index, item in enumerate(recs, start=1):
        if isinstance(item, str):
            if not item.strip():
                errors.append(f"business_recommendations[{index}] vide")
            continue
        if isinstance(item, dict):
            missing = [
                field
                for field in ("title", "why", "example", "expected_impact")
                if not isinstance(item.get(field), str) or not item.get(field).strip()
            ]
            if missing:
                errors.append(f"business_recommendations[{index}] structure incomplète: {','.join(missing)}")
            continue
        errors.append(f"business_recommendations[{index}] type invalide")
    return errors


def _contains_high_risk_forbidden(text: str) -> list[str]:
    errors = []
    if "risque élevé" in text or "risque eleve" in text:
        allowed = (
            "aucun client à risque élevé",
            "aucun client a risque eleve",
            "aucun profil à risque élevé",
            "aucun profil a risque eleve",
            "absence de clients à risque élevé",
            "absence de clients a risque eleve",
        )
        if not any(phrase in text for phrase in allowed):
            errors.append("risque élevé")
    errors.extend(_contains_any(text, NO_HIGH_FORBIDDEN))
    return errors


def _contains_no_anomaly_forbidden(text: str) -> list[str]:
    errors = _contains_any(text, NO_ANOMALY_FORBIDDEN)
    if "avec anomalie" in text:
        errors.append("avec anomalie")
    return errors


def _validate_response(payload: dict[str, Any], response: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    report = response.get("report") or {}
    kpis = response.get("kpis") or {}
    text = _report_text(report)
    text_l = text.lower()
    decision_text_l = _decision_support_text(report).lower()

    for field in REQUIRED_REPORT_FIELDS:
        if field not in report or report.get(field) in (None, "", []):
            errors.append(f"champ manquant: {field}")

    title_payload = response.get("filters") or payload
    expected_title = _global_report_title(title_payload, int(kpis.get("total_clients") or 0))
    if report.get("report_title") != expected_title:
        errors.append(f"titre incohérent: attendu '{expected_title}', reçu '{report.get('report_title')}'")

    if not isinstance(report.get("decision_support"), list) or not report.get("decision_support"):
        errors.append("decision_support invalide")
    for raw in DECISION_SUPPORT_RAW_FORBIDDEN:
        if re.search(rf"\b{re.escape(raw)}\b", decision_text_l):
            errors.append(f"decision_support label technique: {raw}")
    if not isinstance(report.get("main_findings"), list) or not report.get("main_findings"):
        errors.append("main_findings invalide")
    errors.extend(_validate_business_recommendations(report))
    if not isinstance(report.get("profile_recommendations"), list) or not report.get("profile_recommendations"):
        errors.append("profile_recommendations invalide")
    if not isinstance(report.get("business_rationale"), list) or not report.get("business_rationale"):
        errors.append("business_rationale invalide")

    for term in _contains_forbidden_terms(text_l, TECHNICAL_FORBIDDEN):
        errors.append(f"terme technique visible: {term}")
    for phrase in _contains_any(text_l, WEAK_PHRASES):
        errors.append(f"phrase faible: {phrase}")

    total = int(kpis.get("total_clients") or 0)
    clients_high = int(kpis.get("clients_high") or 0)
    clients_anomaly = int(kpis.get("clients_with_anomaly") or 0)
    avg_reimb = kpis.get("average_reimbursement_ratio")
    avg_debt = kpis.get("average_debt")

    if payload.get("is_anomaly") is False or clients_anomaly == 0:
        for term in _contains_no_anomaly_forbidden(text_l):
            errors.append(f"mention anomalie interdite: {term}")

    if clients_high == 0:
        for term in _contains_high_risk_forbidden(text_l):
            errors.append(f"contradiction risque high=0: {term}")
        if re.search(r"\b[1-9]\d*\s+clients?\s+à\s+risque\s+élev", decision_text_l):
            errors.append("decision_support clients_high > 0 alors que KPI=0")
        if any(term in decision_text_l for term in ("traitement prioritaire", "profils les plus exposés")):
            errors.append("decision_support prioritaire alors que clients_high=0")

    clients_medium = int(kpis.get("clients_medium") or 0)
    clients_low = int(kpis.get("clients_low") or 0)
    if clients_medium == 0 and re.search(r"\b[1-9]\d*\s+clients?\s+à\s+risque\s+moyen", decision_text_l):
        errors.append("decision_support clients_medium > 0 alors que KPI=0")
    if clients_low == 0 and re.search(r"\b[1-9]\d*\s+clients?\s+à\s+risque\s+faible", decision_text_l):
        errors.append("decision_support clients_low > 0 alors que KPI=0")

    if payload.get("risk_tier") == "low":
        for term in _contains_any(text_l, LOW_RISK_FORBIDDEN):
            errors.append(f"terme interdit risque faible: {term}")

    if avg_reimb is not None and float(avg_reimb) >= 0.95:
        for term in _contains_any(text_l, GOOD_REIMBURSEMENT_FORBIDDEN):
            errors.append(f"contradiction remboursement >=95%: {term}")

    if avg_debt is not None and float(avg_debt) == 0:
        for term in _contains_any(text_l, ZERO_DEBT_FORBIDDEN):
            errors.append(f"contradiction dette=0: {term}")

    if (
        payload.get("cluster_name") == "Bon-payeur"
        and payload.get("is_anomaly") is not True
        and avg_debt is not None
        and float(avg_debt) == 0
        and avg_reimb is not None
        and float(avg_reimb) >= 0.95
    ):
        for term in _contains_any(text_l, BON_PAYEUR_STABLE_FORBIDDEN):
            errors.append(f"contradiction Bon payeur stable: {term}")

    if (
        payload.get("cluster_name") == "Bon-payeur"
        and payload.get("is_anomaly") is True
        and clients_high == 0
        and avg_debt is not None
        and float(avg_debt) == 0
        and avg_reimb is not None
        and float(avg_reimb) >= 0.95
    ):
        for term in _contains_any(text_l, BON_PAYEUR_ANOMALY_STABLE_FORBIDDEN):
            errors.append(f"contradiction Bon payeur anomalie stable: {term}")
        if (
            "traitement prioritaire" in text_l
            and "sans traitement prioritaire" not in text_l
            and "ne pas mobiliser un traitement prioritaire" not in text_l
        ):
            errors.append("contradiction Bon payeur anomalie stable: traitement prioritaire")

    if total == 0:
        rec_text = " ".join(
            " ".join(str(item.get(field) or "") for field in ("title", "why", "example", "expected_impact"))
            if isinstance(item, dict)
            else str(item)
            for item in (report.get("business_recommendations") or [])
        ).lower()
        for term in _contains_any(rec_text, EMPTY_RECOMMENDATION_FORBIDDEN):
            errors.append(f"recommandation incohérente aucun résultat: {term}")

    if payload.get("recommended_action") == "sms_retention_offer":
        for term in _contains_any(text_l, SMS_FORBIDDEN):
            errors.append(f"terme commercial interdit SMS: {term}")

    if payload.get("search"):
        precise_exception = (
            "n'est pas une tendance globale" in text_l
            or "ne représente pas une tendance globale" in text_l
            or "ne represente pas une tendance globale" in text_l
        )
        if not precise_exception:
            for term in _contains_any(text_l, SEARCH_GLOBAL_FORBIDDEN):
                errors.append(f"recherche MSISDN trop globale: {term}")
        if total > 0 and not any(term in text_l for term in ("périmètre réduit", "perimetre reduit", "recherche", "client ciblé", "client cible")):
            errors.append("recherche MSISDN sans mention de périmètre réduit ou ciblé")

    if not _generated_numbers_are_allowed(_global_report_number_narrative(report), _allowed_global_numbers(kpis)):
        errors.append("chiffre inventé détecté")

    return _filter_standard_response_errors(payload, text_l, errors)


def _filter_standard_response_errors(payload: dict[str, Any], text_l: str, errors: list[str]) -> list[str]:
    if payload.get("cluster_name") != "Bon-payeur" or payload.get("risk_tier") != "medium":
        return errors
    allowed_phrase = (
        "sans traitement prioritaire" in text_l
        or ("sans d" in text_l and "clencher de traitement prioritaire" in text_l)
        or "ne pas mobiliser un traitement prioritaire" in text_l
    )
    if allowed_phrase:
        errors = [
            error for error in errors
            if error not in {
                "decision_support prioritaire alors que clients_high=0",
                "contradiction Bon payeur stable: traitement prioritaire",
                "contradiction Bon payeur anomalie stable: traitement prioritaire",
            }
        ]
    return [
        error for error in errors
        if not error.startswith("contradiction Bon payeur stable: risque ")
    ]


def _print_row(case_number: int, payload: dict[str, Any], source: str, repaired: bool, fallback: bool, seconds: float | None, result: str, errors: list[str]) -> None:
    payload_text = console_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    error_text = " - " if not errors else console_text(" ; ".join(errors))
    seconds_text = "-" if seconds is None else f"{seconds:.1f}s"
    rep_text = "OUI" if repaired else "NON"
    fb_text = "OUI" if fallback else "NON"
    safe_print(f"CAS {case_number:02d} | {payload_text:<60} | {source:<15} | {rep_text:<8} | {fb_text:<8} | {seconds_text:<6} | {result:<6} | {error_text}", flush=True)


def _print_detailed_report(case_number: int, payload: dict[str, Any], response: dict[str, Any], elapsed: float, errors: list[str]) -> None:
    report = response.get("report") or {}
    source = response.get("report_source") or "unknown"
    gen = response.get("report_generation") or {}
    fallback_reason = gen.get("fallback_reason") or "N/A"
    
    is_fallback = source == "deterministic_fallback"
    is_repaired = source == "local_llm" and not is_fallback
    
    safe_print("\n" + "="*80)
    safe_print(f"RAPPORT DÉTAILLÉ - CAS {case_number:02d}")
    safe_print("="*80)
    safe_print(f"PAYLOAD   : {console_text(json.dumps(payload, ensure_ascii=False))}")
    safe_print(f"MODÈLE    : {console_text(gen.get('primary_model') or gen.get('model'))}")
    safe_print(f"BACKUP    : {'OUI' if gen.get('backup_used') else 'NON'}")
    safe_print(f"SOURCE    : {console_text(source)}")
    safe_print(f"TEMPS     : {elapsed:.2f}s")
    safe_print(f"REPAIRED  : {'OUI' if is_repaired else 'NON'}")
    safe_print(f"FALLBACK  : {'OUI' if is_fallback else 'NON'}")
    safe_print(f"REASON    : {console_text(fallback_reason)}")
    safe_print(f"RESULTAT  : {'OK' if not errors else 'FAIL'}")
    if errors:
        safe_print(f"ERREURS   : {console_text('; '.join(errors))}")
    safe_print("-" * 40)
    safe_print(f"TITRE : {console_text(report.get('report_title'))}")
    summary = report.get('executive_summary') or ""
    first_sent = summary.split('.')[0] if '.' in summary else summary
    safe_print(f"PREMIÈRE PHRASE RÉSUMÉ : {console_text(first_sent)}...")
    safe_print(f"LECTURE MÉTIER          : {console_text(report.get('risk_reading'))}")
    safe_print(f"NARRATIVE RECOMMAND.    : {console_text(report.get('internal_note'))}")
    
    ds = report.get('decision_support') or []
    if ds:
        p1 = ds[0]
        safe_print(f"PREMIÈRE PRIORITÉ      : {console_text(p1.get('priority'))} -> {console_text(p1.get('recommended_focus'))}")
    
    br = report.get('business_recommendations') or []
    if br:
        r1 = br[0]
        safe_print(f"PREMIÈRE RECOMMANDATION : {console_text(r1.get('title') if isinstance(r1, dict) else r1)}")
    safe_print("="*80 + "\n")


RISK_FILTER_VALUES = (None, "low", "medium", "high")
SEGMENT_FILTER_VALUES = (None, "Standard", "Bon-payeur", "SUSPENDED", "DISCONNECTED", "ON-HOLD")
ANOMALY_FILTER_VALUES = (None, True, False)
ACTION_FILTER_VALUES = (None, "call_center_priority", "sms_retention_offer", "monitor_only")
SEARCH_FILTER_VALUES = ("2169", "000000000000000000")


def _clean_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None and value != ""}


def _generate_exhaustive_filter_payloads() -> list[dict[str, Any]]:
    seen: set[str] = set()
    payloads: list[dict[str, Any]] = []

    def add(payload: dict[str, Any]) -> None:
        item = _clean_payload(payload)
        key = json.dumps(item, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        if key not in seen:
            seen.add(key)
            payloads.append(item)

    for risk, segment, anomaly, action in itertools.product(
        RISK_FILTER_VALUES,
        SEGMENT_FILTER_VALUES,
        ANOMALY_FILTER_VALUES,
        ACTION_FILTER_VALUES,
    ):
        add({
            "risk_tier": risk,
            "cluster_name": segment,
            "is_anomaly": anomaly,
            "recommended_action": action,
        })

    for search in SEARCH_FILTER_VALUES:
        add({"search": search})
        for risk in RISK_FILTER_VALUES[1:]:
            add({"search": search, "risk_tier": risk})
        for segment in SEGMENT_FILTER_VALUES[1:]:
            add({"search": search, "cluster_name": segment})
        for anomaly in ANOMALY_FILTER_VALUES[1:]:
            add({"search": search, "is_anomaly": anomaly})

    return payloads


def _validate_exhaustive_response(original_payload: dict[str, Any], response: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    report = response.get("report") or {}
    kpis = response.get("kpis") or {}
    returned_filters = response.get("filters") or original_payload
    title = str(report.get("report_title") or "")
    text = _report_text(report)
    text_l = text.lower()
    title_l = title.lower()
    total = int(kpis.get("total_clients") or 0)
    high = int(kpis.get("clients_high") or 0)
    anomaly = int(kpis.get("clients_with_anomaly") or 0)
    avg_reimb = kpis.get("average_reimbursement_ratio")
    avg_debt = kpis.get("average_debt")

    for field in REQUIRED_REPORT_FIELDS:
        if field not in report or report.get(field) in (None, "", []):
            errors.append(f"champ manquant: {field}")
    if not _generated_numbers_are_allowed(_global_report_number_narrative(report), _allowed_global_numbers(kpis)):
        errors.append("chiffre inventé détecté")
    for term in _contains_forbidden_terms(text_l, TECHNICAL_FORBIDDEN):
        errors.append(f"terme technique visible: {term}")

    if total > 0 and not original_payload.get("search") and returned_filters.get("cluster_name") == "Bon-payeur" and "bon payeur" not in title_l:
        errors.append("titre sans segment Bon payeur")
    if total > 0 and not original_payload.get("search") and returned_filters.get("risk_tier") == "medium" and "risque moyen" not in title_l:
        errors.append("titre sans risque moyen")
    if returned_filters.get("is_anomaly") is True and anomaly == total and total > 0:
        if "anomalie" not in title_l and returned_filters.get("is_anomaly") is not True:
            errors.append("anomalie totale non visible titre/filtres")
    if total == 0:
        if "aucun r" not in title_l and "aucun client" not in title_l:
            errors.append("titre aucun résultat absent")
        summary = str(report.get("executive_summary") or "").lower()
        recs = json.dumps(report.get("business_recommendations") or [], ensure_ascii=False, default=str).lower()
        if "aucun client ne correspond" not in summary:
            errors.append("résumé aucun résultat incohérent")
        if not any(term in recs for term in ("élargir", "réinitialiser", "modifier les filtres", "retirer un filtre")):
            errors.append("recommandation aucun résultat sans élargir/réinitialiser")
    if original_payload.get("search"):
        if "recherche" not in title_l and "recherche" not in text_l and "périmètre ciblé" not in text_l and "périmètre réduit" not in text_l:
            errors.append("recherche sans mention ciblée")
    if returned_filters:
        forbidden_current_scope = ("100 % du portefeuille", "100% du portefeuille", "tout le portefeuille", "ensemble du portefeuille")
        for term in forbidden_current_scope:
            if term in text_l:
                errors.append(f"périmètre filtré présenté comme portefeuille: {term}")
    if high == 0 and any(term in text_l for term in ("traitement prioritaire massif", "urgence prioritaire", "cas critiques")):
        errors.append("priorité excessive alors que clients_high=0")
    if returned_filters.get("risk_tier") == "medium":
        if "urgence critique" in text_l or "priorité absolue" in text_l:
            errors.append("risque moyen dramatisé")
        if "crise" in text_l and "sans lecture de crise" not in text_l:
            errors.append("risque moyen dramatisé")
    if returned_filters.get("risk_tier") == "high" and total > 0 and not any(term in text_l for term in ("prior", "expos", "suivi")):
        errors.append("risque élevé sans logique de priorisation")
    if (returned_filters.get("is_anomaly") is False or anomaly == 0) and any(term in text_l for term in ("profils anomaliques", "anomalies présentes", "avec anomalie")):
        errors.append("anomalie mentionnée dans périmètre sans anomalie")
    if returned_filters.get("is_anomaly") is True and "preuve automatique" in text_l:
        if not any(term in text_l for term in ("pas une preuve automatique", "pas comme une preuve automatique", "pas comme preuve automatique")):
            errors.append("anomalie présentée comme preuve automatique")
    if returned_filters.get("is_anomaly") is True and "conclusion automatique" in text_l:
        if "pas une conclusion automatique" not in text_l:
            errors.append("anomalie présentée comme conclusion automatique")
    if avg_reimb is not None and float(avg_reimb) >= 0.95:
        for term in ("remboursement faible", "remboursement dégradé", "remboursement moins régulier", "baisse de remboursement"):
            if term in text_l:
                errors.append(f"contradiction remboursement >=95%: {term}")
    if avg_debt is not None and float(avg_debt) == 0:
        for term in ("dette active", "encours actif", "exposition financière", "montant à recouvrer", "impayé actif"):
            if term in text_l:
                errors.append(f"contradiction dette=0: {term}")
    if returned_filters.get("recommended_action") == "call_center_priority":
        for term in ("sanction", "menace", "contentieux", "poursuite"):
            if term in text_l:
                errors.append(f"terme agressif appel prioritaire: {term}")
    if returned_filters.get("recommended_action") == "monitor_only" and any(term in text_l for term in ("urgence", "critique", "traitement prioritaire")):
        allowed = ("sans traitement prioritaire", "ne pas mobiliser un traitement prioritaire")
        if not any(term in text_l for term in allowed):
            errors.append("suivi routine dramatisé")
    return list(dict.fromkeys(errors))


def _run_exhaustive_filters(service: BadDebtsService) -> int:
    start = time.perf_counter()
    payloads = _generate_exhaustive_filter_payloads()
    failures: list[tuple[dict[str, Any], str, list[str]]] = []
    ok_count = 0
    empty_count = 0

    safe_print("Validation exhaustive des filtres Bad Debts (mode Python rapide)", flush=True)
    safe_print(f"{'CAS':<6} | {'PAYLOAD':<95} | {'TOTAL_CLIENTS':<13} | {'TITLE':<70} | {'RESULT':<6} | ERRORS", flush=True)
    safe_print("-" * 220, flush=True)

    for index, payload in enumerate(payloads, start=1):
        try:
            response = generate_global_llm_report(service, payload)
            report = response.get("report") or {}
            kpis = response.get("kpis") or {}
            total = int(kpis.get("total_clients") or 0)
            if total == 0:
                empty_count += 1
            errors = _validate_exhaustive_response(payload, response)
            title = console_text(report.get("report_title") or "")
            result = "OK" if not errors else "FAIL"
            if errors:
                failures.append((payload, title, errors))
            else:
                ok_count += 1
            payload_text = console_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
            error_text = "-" if not errors else console_text(" ; ".join(errors[:4]))
            safe_print(f"{index:<6} | {payload_text:<95} | {total:<13} | {title[:70]:<70} | {result:<6} | {error_text}", flush=True)
        except Exception as exc:  # noqa: BLE001
            errors = [f"exception: {type(exc).__name__}: {exc}"]
            failures.append((payload, "-", errors))
            payload_text = console_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
            safe_print(f"{index:<6} | {payload_text:<95} | {'-':<13} | {'-':<70} | {'FAIL':<6} | {console_text(errors[0])}", flush=True)

    elapsed = time.perf_counter() - start
    total_count = len(payloads)
    safe_print("-" * 220, flush=True)
    safe_print(f"Total combinaisons testées : {total_count}", flush=True)
    safe_print(f"OK : {ok_count}", flush=True)
    safe_print(f"FAIL : {len(failures)}", flush=True)
    safe_print(f"Aucun résultat : {empty_count}", flush=True)
    safe_print(f"Temps total : {elapsed:.2f}s", flush=True)
    if failures:
        safe_print("\nSynthèse des échecs :", flush=True)
        for payload, title, errors in failures[:80]:
            payload_text = console_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
            safe_print(f"- {payload_text} | {console_text(title)} | {console_text(' ; '.join(errors))}", flush=True)
        if len(failures) > 80:
            safe_print(f"... {len(failures) - 80} échecs supplémentaires non affichés.", flush=True)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Teste automatiquement la cohérence des rapports globaux Bad Debts.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Arrêter le script au premier cas en échec.",
    )
    parser.add_argument(
        "--ollama-timeout-seconds",
        type=int,
        default=None,
        help="Limiter le temps d'attente du moteur de rédaction local pendant ce test, puis fallback si le délai est dépassé.",
    )
    parser.add_argument(
        "--case",
        type=int,
        default=None,
        help="Numéro d'un seul cas à exécuter.",
    )
    parser.add_argument(
        "--from-case",
        type=int,
        default=None,
        help="Démarrer à partir de ce numéro de cas.",
    )
    parser.add_argument(
        "--to-case",
        type=int,
        default=None,
        help="S'arrêter à ce numéro de cas (inclus).",
    )
    parser.add_argument(
        "--cases",
        default="",
        help="Liste de numéros de cas à exécuter, séparés par des virgules. Exemple: 1,9,16",
    )
    parser.add_argument(
        "--only-smoke",
        action="store_true",
        help="Exécuter uniquement 3 cas pour valider l'IA rapidement.",
    )
    parser.add_argument(
        "--exhaustive-filters",
        action="store_true",
        help="Tester automatiquement les combinaisons utiles de filtres en mode rapide.",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Désactiver Ollama pour tester uniquement la logique Python (fallback).",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Modèle Ollama à utiliser pour le test.",
    )
    args = parser.parse_args()

    if args.no_llm:
        settings.BAD_DEBTS_OLLAMA_ENABLED = False

    if args.ollama_timeout_seconds is not None:
        settings.BAD_DEBTS_OLLAMA_TIMEOUT_SECONDS = args.ollama_timeout_seconds
        
    if args.model is not None:
        settings.BAD_DEBTS_OLLAMA_MODEL = args.model

    safe_print(f"Validation automatique des rapports globaux Bad Debts ({len(PAYLOADS)} cas)", flush=True)
    safe_print(f"Moteur local activé: {bool(settings.BAD_DEBTS_OLLAMA_ENABLED)}", flush=True)
    safe_print(f"Modèle configuré: {settings.BAD_DEBTS_OLLAMA_MODEL}", flush=True)
    safe_print(f"Timeout Ollama: {settings.BAD_DEBTS_OLLAMA_TIMEOUT_SECONDS}s", flush=True)
    
    if args.exhaustive_filters and settings.BAD_DEBTS_OLLAMA_ENABLED:
        settings.BAD_DEBTS_OLLAMA_ENABLED = False
        safe_print("Mode exhaustive-filters: moteur local désactivé pour éviter les appels IA.", flush=True)
    if args.exhaustive_filters:
        db = SessionLocal()
        try:
            return _run_exhaustive_filters(BadDebtsService(db))
        finally:
            db.close()

    selected_cases = set()
    if args.case is not None:
        selected_cases.add(args.case)
    elif args.from_case is not None or args.to_case is not None:
        start_c = args.from_case or 1
        end_c = args.to_case or len(PAYLOADS)
        selected_cases = set(range(start_c, end_c + 1))
    elif args.only_smoke:
        selected_cases = {1, 9, 16}
    elif args.cases:
        selected_cases = {
            int(item.strip())
            for item in str(args.cases or "").split(",")
            if item.strip().isdigit()
        }

    is_single_or_small = len(selected_cases) > 0 and len(selected_cases) <= 5

    if not is_single_or_small:
        safe_print("-" * 150, flush=True)
        safe_print(f"{'CAS':<6} | {'PAYLOAD':<60} | {'SOURCE':<15} | {'REPAIRED':<8} | {'FALLBACK':<8} | {'TEMPS':<6} | {'RESULT':<6} | {'ERREURS'}", flush=True)
        safe_print("-" * 150, flush=True)

    ok_count = 0
    failures: list[tuple[int, str, dict[str, Any], list[str]]] = []
    
    db = SessionLocal()
    try:
        service = BadDebtsService(db)
        for index, (name, payload) in enumerate(PAYLOADS, start=1):
            if selected_cases and index not in selected_cases:
                continue
            try:
                start = time.perf_counter()
                response = generate_global_llm_report(service, payload)
                elapsed = time.perf_counter() - start
                
                source = response.get("report_source") or "unknown"
                is_fallback = source == "deterministic_fallback"
                is_repaired = source == "local_llm" # Approximate for table display
                
                errors = _validate_response(payload, response)
                
                if is_single_or_small:
                    _print_detailed_report(index, payload, response, elapsed, errors)
                else:
                    if errors:
                        _print_row(index, payload, source, is_repaired, is_fallback, elapsed, "FAIL", errors)
                    else:
                        _print_row(index, payload, source, is_repaired, is_fallback, elapsed, "OK", [])
                
                if errors:
                    failures.append((index, name, payload, errors))
                    if args.fail_fast:
                        break
                else:
                    ok_count += 1

            except Exception as exc:  # noqa: BLE001
                errors = [f"exception: {type(exc).__name__}: {exc}"]
                failures.append((index, name, payload, errors))
                if is_single_or_small:
                    safe_print(f"ERREUR CRITIQUE CAS {index}: {console_text(errors[0])}")
                else:
                    _print_row(index, payload, "exception", False, False, None, "FAIL", errors)
                if args.fail_fast:
                    break
    finally:
        db.close()

    if not is_single_or_small:
        total = ok_count + len(failures)
        safe_print("-" * 150, flush=True)
        safe_print(f"Total tests : {total}", flush=True)
        safe_print(f"OK : {ok_count}", flush=True)
        safe_print(f"FAIL : {len(failures)}", flush=True)

    if failures:
        safe_print("\nSynthèse des échecs :", flush=True)
        for index, name, payload, errors in failures:
            payload_text = console_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
            safe_print(f"- CAS {index} ({name}) {payload_text}: {console_text(' ; '.join(errors))}", flush=True)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
