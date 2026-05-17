from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agents.nodes import _validate_contact_message
from app.services.bad_debts_agent_service import build_explanations, decide_next_action, generate_message
from app.services.bad_debts_llm_report_service import fallback_client_report, validate_client_llm_report


def _client(**overrides):
    base = {
        "msisdn": "21690000000",
        "cluster_name": "Standard",
        "state": "ACTIVE",
        "risk_tier": "medium",
        "final_risk_score": 0.42,
        "is_anomaly": False,
        "total_outstanding_amount": 10.0,
        "avg_reimburse_ratio": 0.72,
        "debt_to_credit": 0.2,
        "nb_sos": 3,
        "top_drivers": [{"feature": "avg_credit_amount"}],
    }
    base.update(overrides)
    return base


def _decision(client):
    return decide_next_action(client, build_explanations(client))


def _context(client, decision, message):
    return {
        "client": {
            "msisdn_masked": "216*****000",
            "cluster_name": client.get("cluster_name"),
            "state": client.get("state"),
            "raw_risk_tier": decision.get("raw_risk_tier"),
            "effective_tier": decision.get("effective_tier"),
            "final_risk_score": client.get("final_risk_score"),
            "is_anomaly": bool(client.get("is_anomaly")),
            "total_outstanding_amount": client.get("total_outstanding_amount"),
            "avg_reimburse_ratio": client.get("avg_reimburse_ratio"),
            "debt_to_credit": client.get("debt_to_credit"),
            "nb_sos": client.get("nb_sos"),
            "top_drivers": ["Montant moyen crédité"],
        },
        "decision": {
            "recommended_action": decision.get("recommended_action"),
            "recommended_action_label": decision.get("recommended_action_label"),
            "priority": decision.get("priority"),
            "priority_label": decision.get("priority_label"),
            "next_best_action": decision.get("next_best_action"),
        },
        "contact_proposal": message,
        "deterministic_analysis": {
            "key_risk_factors": ["Niveau de risque effectif moyen", "Score ML 0.42"],
        },
    }


def _assert(condition, label):
    if not condition:
        raise AssertionError(label)
    print(f"OK | {label}")


def main() -> int:
    high = _client(cluster_name="DISCONNECTED", risk_tier="high", is_anomaly=False)
    high_decision = _decision(high)
    high_message = generate_message(high, high_decision)
    _assert(high_decision["recommended_action"] == "call_center_priority", "high action appel prioritaire")
    _assert(high_message["contact_type"] == "call_script", "high proposition script conseiller")
    _assert(high_message["safe_to_send"] is False, "high safe_to_send false")
    _assert("sms" not in high_message["message_text"].lower(), "high pas de SMS direct")
    _assert(high_message["message_text"] == "Qualifier la situation client via le centre de relation client avant toute action métier.", "high script interne court")
    _assert(_validate_contact_message(high_message, high, high_decision), "high message valide")
    bad_high = {**high_message, "message_text": "SMS envoyé avec menace de contentieux."}
    _assert(not _validate_contact_message(bad_high, high, high_decision), "high menace/SMS rejeté")

    medium = _client(cluster_name="Standard", risk_tier="medium", is_anomaly=False)
    medium_decision = _decision(medium)
    medium_message = generate_message(medium, medium_decision)
    _assert(medium_decision["recommended_action"] == "sms_retention_offer", "medium action SMS")
    _assert(medium_message["contact_type"] == "preventive_sms", "medium proposition SMS préventif")
    _assert(medium_message["safe_to_send"] is True, "medium safe_to_send true")
    bad_medium = {**medium_message, "message_text": "Profitez d'une remise et d'une offre commerciale."}
    _assert(not _validate_contact_message(bad_medium, medium, medium_decision), "medium offre commerciale rejetée")

    low = _client(cluster_name="Bon-payeur", risk_tier="low", is_anomaly=False, total_outstanding_amount=0, avg_reimburse_ratio=1)
    low_decision = _decision(low)
    low_message = generate_message(low, low_decision)
    _assert(low_decision["recommended_action"] == "monitor_only", "low action suivi routine")
    _assert(low_message["contact_type"] == "monitoring_note", "low note de suivi")
    _assert(low_message["message_text"] == "Suivi routine — aucune action immédiate.", "low suivi routine court")
    _assert("urgent" not in low_message["message_text"].lower(), "low pas de dramatisation")

    no_debt = {**medium_message, "message_text": "Bonjour, un suivi neutre est proposé pour votre ligne sans dette active."}
    _assert(not _validate_contact_message(no_debt, low, low_decision), "dette 0 rejette dette active")
    anomaly_false = {**medium_message, "message_text": "Bonjour, une anomalie détectée nécessite un suivi."}
    _assert(not _validate_contact_message(anomaly_false, medium, medium_decision), "anomalie false rejette anomalie")
    reimb_full = {**medium_message, "message_text": "Bonjour, remboursement faible détecté sur votre ligne."}
    _assert(not _validate_contact_message(reimb_full, low, low_decision), "remboursement 100 rejette remboursement faible")

    report = fallback_client_report(_context(medium, medium_decision, medium_message))
    _assert(validate_client_llm_report(report, _context(medium, medium_decision, medium_message)), "rapport client fallback valide")
    _assert("kpis" not in report and "recommendation" not in report and "factors" not in report, "rapport client sans redondance drawer")
    _assert(report.get("sms_proposal"), "rapport medium contient SMS proposé")
    high_report = fallback_client_report(_context(high, high_decision, high_message))
    low_report = fallback_client_report(_context(low, low_decision, low_message))
    _assert(high_report.get("sms_proposal") is None, "rapport high sans SMS")
    _assert(low_report.get("sms_proposal") is None, "rapport low sans SMS")
    bad_report = {**report, "manager_summary": "fallback technique local_llm API JSON"}
    _assert(not validate_client_llm_report(bad_report, _context(medium, medium_decision, medium_message)), "rapport rejette termes techniques")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
