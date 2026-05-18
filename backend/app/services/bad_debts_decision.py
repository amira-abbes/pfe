from __future__ import annotations

from typing import Any


ACTION_BUSINESS_LABELS = {
    "call_center_priority": "Appel prioritaire centre de relation client",
    "sms_retention_offer": "SMS personnalisé",
    "monitor_only": "Suivi routine",
}

PRIORITY_BUSINESS_LABELS = {
    1: "Très urgent",
    2: "Urgent",
    4: "Normal",
}

DECISION_POLICY_VERSION = "pfee-client-treatment-deterministic-v1"


def normalize_risk_tier(value: Any) -> str:
    tier = str(value or "low").strip().lower()
    return tier if tier in {"low", "medium", "high"} else "low"


def effective_risk_tier(client: dict[str, Any] | None) -> str:
    item = client or {}
    tier = normalize_risk_tier(item.get("risk_tier"))
    if bool(item.get("is_anomaly")) and tier == "medium":
        return "high"
    if bool(item.get("is_anomaly")) and tier == "low":
        return "medium"
    return tier


def compute_client_decision(client: dict[str, Any] | None) -> dict[str, Any]:
    item = client or {}
    raw_tier = normalize_risk_tier(item.get("risk_tier"))
    effective_tier = effective_risk_tier(item)
    if effective_tier == "high":
        action = "call_center_priority"
        priority = 1
        next_best_action = "Qualifier la situation client avec un appel prioritaire centre de relation client"
    elif effective_tier == "medium":
        action = "sms_retention_offer"
        priority = 2
        next_best_action = "Envoyer SMS personnalisé"
    else:
        action = "monitor_only"
        priority = 4
        next_best_action = "Aucune action immédiate — suivi routine"
    return {
        "recommended_action": action,
        "recommended_action_label": ACTION_BUSINESS_LABELS[action],
        "priority": priority,
        "priority_label": PRIORITY_BUSINESS_LABELS[priority],
        "next_best_action": next_best_action,
        "raw_risk_tier": raw_tier,
        "effective_tier": effective_tier,
        "anomaly_escalated": bool(item.get("is_anomaly")) and effective_tier != raw_tier,
    }
