from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from langgraph.graph import END, StateGraph

from app.agents.state import AgentState
from app.agents.nodes import (
    ai_analysis_node,
    decision_node,
    explainability_node,
    message_generation_node,
    monitoring_node,
    profiling_node,
)
from app.services.bad_debts_agent_service import (
    DECISION_POLICY_VERSION,
    build_client_ml_signature,
    get_reusable_agent_run_response,
)
from app.services.bad_debts_service import BadDebtsService


def build_agent_graph():
    graph = StateGraph(AgentState)

    graph.add_node("profiling", profiling_node)
    graph.add_node("explainability", explainability_node)
    graph.add_node("decision", decision_node)
    graph.add_node("ai_analysis", ai_analysis_node)
    graph.add_node("message_generation", message_generation_node)
    graph.add_node("monitoring", monitoring_node)

    graph.set_entry_point("profiling")
    graph.add_edge("profiling", "explainability")
    graph.add_edge("explainability", "decision")
    graph.add_edge("decision", "ai_analysis")
    graph.add_conditional_edges(
        "ai_analysis",
        _route_after_decision,
        {
            "monitoring": "monitoring",
            "message_generation": "message_generation",
        },
    )
    graph.add_edge("message_generation", "monitoring")
    graph.add_edge("monitoring", END)

    return graph


def get_graph():
    return build_agent_graph().compile()


def run_agent_graph(
    msisdn: str,
    features: dict[str, float] | None = None,
    ml_outputs: dict[str, Any] | None = None,
    db: Any = None,
    client: dict[str, Any] | Any | None = None,
    enable_llm: bool = True,
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    errors: list[str] = []
    resolved_client = client

    if resolved_client is None and db is not None:
        try:
            resolved_client = BadDebtsService(db).get_client(msisdn)
            if resolved_client is None:
                errors.append(f"Client introuvable : {msisdn}")
        except Exception as exc:
            errors.append(f"Chargement client impossible : {exc}")

    signature_data: dict[str, Any] = {}
    if db is not None and resolved_client is not None and not errors:
        try:
            signature_data = build_client_ml_signature(_as_dict(resolved_client))
            reusable = get_reusable_agent_run_response(db, msisdn, signature_data["ml_signature"])
            if reusable is not None:
                return reusable
        except Exception as exc:
            errors.append(f"Vérification analyse existante impossible : {exc}")

    initial_state: AgentState = {
        "msisdn": msisdn,
        "features": features or {},
        "ml_outputs": ml_outputs or {},
        "db": db,
        "client": resolved_client,
        "client_found": resolved_client is not None or db is None,
        "enable_llm": enable_llm,
        "run_id": run_id,
        "started_at": datetime.utcnow(),
        "errors": errors,
        "ml_signature": signature_data.get("ml_signature", ""),
        "ml_signature_fields": signature_data.get("ml_signature_fields", {}),
        "decision_policy_version": DECISION_POLICY_VERSION,
    }

    result = get_graph().invoke(initial_state)
    return {
        "run_id": result.get("run_id", run_id),
        "msisdn": result.get("msisdn", msisdn),
        "profile": result.get("profile", {}),
        "explanations": result.get("explanations", {}),
        "decision": result.get("decision", {}),
        "message": result.get("message"),
        "ai_analysis": result.get("ai_analysis", {}),
        "action_id": result.get("action_id"),
        "agent_run_id": result.get("agent_run_id"),
        "errors": result.get("errors", []),
        "reused_existing_analysis": bool(result.get("reused_existing_analysis")),
    }


def run_agent_graph_from_client_row(client: dict[str, Any] | Any, db: Any = None) -> dict[str, Any]:
    client_dict = _as_dict(client)
    return run_agent_graph(
        str(client_dict.get("msisdn") or ""),
        features={},
        ml_outputs={},
        db=db,
        client=client_dict,
    )


def _route_after_decision(state: AgentState) -> str:
    decision = state.get("decision") or {}
    if decision.get("action_type") == "monitor_only":
        return "monitoring"
    return "message_generation"


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
