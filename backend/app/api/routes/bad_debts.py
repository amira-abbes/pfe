from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.agents.graph import run_agent_graph
from app.db.database import get_db
from app.schemas.bad_debts import (
    BadDebtClientDetail,
    BadDebtClientsPage,
    BadDebtsClientReportResponse,
    BadDebtsGlobalReportResponse,
    BadDebtsHealthResponse,
    BadDebtsSummary,
    BadDebtsAgentResponse,
    GlobalReportFilters,
    ImportRunItem,
)
from app.services.bad_debts_agent_service import (
    AgentRunError,
    run_bad_debts_agent,
)
from app.services.bad_debts_llm_report_service import generate_client_llm_report, generate_global_llm_report
from app.services.bad_debts_service import BadDebtsService


router = APIRouter(prefix="/api/v1", tags=["Bad Debts ML"])


def get_bad_debts_service(db: Session = Depends(get_db)) -> BadDebtsService:
    return BadDebtsService(db)


@router.get("/bad-debts/health", response_model=BadDebtsHealthResponse)
def bad_debts_health(service: BadDebtsService = Depends(get_bad_debts_service)):
    return service.health()


@router.get("/bad-debts/metrics/summary", response_model=BadDebtsSummary)
def bad_debts_metrics_summary(service: BadDebtsService = Depends(get_bad_debts_service)):
    return service.get_summary()


@router.get("/bad-debts/clients", response_model=BadDebtClientsPage)
def list_bad_debt_clients(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    risk_tier: str | None = Query(default=None),
    cluster_name: str | None = Query(default=None),
    is_anomaly: bool | None = Query(default=None),
    recommended_action: str | None = Query(default=None),
    search: str | None = Query(default=None),
    service: BadDebtsService = Depends(get_bad_debts_service),
):
    return service.list_clients(
        page=page,
        page_size=page_size,
        risk_tier=risk_tier,
        cluster_name=cluster_name,
        is_anomaly=is_anomaly,
        recommended_action=recommended_action,
        search=search,
    )


@router.get("/bad-debts/clients/at-risk", response_model=BadDebtClientsPage)
def list_bad_debt_at_risk_clients(
    tier: str = Query(default="high"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    service: BadDebtsService = Depends(get_bad_debts_service),
):
    return service.list_at_risk_clients(tier=tier, page=page, page_size=page_size)


@router.post("/bad-debts/clients/{msisdn}/run-agent", response_model=BadDebtsAgentResponse)
def run_bad_debt_agent(msisdn: str, db: Session = Depends(get_db)):
    try:
        graph_result = run_agent_graph(msisdn, db=db)
        if _is_client_not_found(graph_result, msisdn):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Client introuvable : {msisdn}",
            )
        return _bad_debts_agent_api_response(msisdn, graph_result)
    except HTTPException:
        raise
    except Exception:
        try:
            response = run_bad_debts_agent(db, msisdn)
        except AgentRunError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "status": "failed",
                    "message": "Erreur lors de l'exécution de l'analyse automatique.",
                    "errors": [str(exc)],
                },
            ) from exc
        if not response:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Client introuvable : {msisdn}",
            )
        return _bad_debts_agent_api_response(msisdn, response)


@router.post("/bad-debts/clients/{msisdn}/report", response_model=BadDebtsClientReportResponse)
def generate_bad_debt_client_report(msisdn: str, db: Session = Depends(get_db)):
    response = generate_client_llm_report(db, msisdn)
    if not response:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Client introuvable : {msisdn}",
        )
    return response


@router.post("/bad-debts/reporting/global", response_model=BadDebtsGlobalReportResponse)
def generate_global_bad_debts_report(
    filters: GlobalReportFilters,
    service: BadDebtsService = Depends(get_bad_debts_service),
):
    return generate_global_llm_report(service, filters.model_dump(exclude_none=False))


def _bad_debts_agent_api_response(msisdn: str, result: dict[str, Any]) -> dict[str, Any]:
    decision = dict(result.get("decision") or {})
    action_id = result.get("action_id") or decision.get("stored_action_id")
    if action_id is not None:
        decision.setdefault("stored_action_id", action_id)

    message = result.get("message") or _fallback_agent_message(decision)

    return {
        "run_id": str(result.get("run_id") or ""),
        "action_id": action_id,
        "agent_run_id": result.get("agent_run_id"),
        "msisdn": str(result.get("msisdn") or msisdn),
        "profile": result.get("profile") or {},
        "explanations": result.get("explanations") or {},
        "decision": decision,
        "message": message,
        "ai_analysis": result.get("ai_analysis") or {},
        "errors": result.get("errors") or [],
        "reused_existing_analysis": bool(result.get("reused_existing_analysis")),
    }


def _fallback_agent_message(decision: dict[str, Any]) -> dict[str, Any]:
    action_type = decision.get("action_type") or decision.get("recommended_action")
    if action_type == "monitor_only":
        return {
            "channel": "monitoring",
            "message_text": "Aucune action client immediate. Suivi automatique recommande.",
            "content": "Aucune action client immediate. Suivi automatique recommande.",
            "language": "fr",
            "safe_to_send": False,
            "generated_by": "template",
            "llm_used": False,
            "llm_model": None,
            "llm_error": None,
            "llm_duration_ms": 0,
            "llm_cache_hit": False,
            "decision_locked": True,
        }
    if action_type == "recovery_review":
        return {
            "channel": "internal_review",
            "message_text": "Traitement interne recommande avant toute communication client.",
            "content": "Traitement interne recommande avant toute communication client.",
            "language": "fr",
            "safe_to_send": False,
            "generated_by": "template",
            "llm_used": False,
            "llm_model": None,
            "llm_error": None,
            "llm_duration_ms": 0,
            "llm_cache_hit": False,
            "decision_locked": True,
        }
    return {
        "channel": "internal",
        "message_text": decision.get("recommendation") or decision.get("next_best_action") or "",
        "content": decision.get("recommendation") or decision.get("next_best_action") or "",
        "language": "fr",
        "safe_to_send": bool(decision.get("safe_to_send")),
        "generated_by": "template",
        "llm_used": False,
        "llm_model": None,
        "llm_error": None,
        "llm_duration_ms": 0,
        "llm_cache_hit": False,
        "decision_locked": True,
    }


def _is_client_not_found(result: dict[str, Any], msisdn: str) -> bool:
    errors = [str(error) for error in (result.get("errors") or [])]
    if not any(f"Client introuvable : {msisdn}" in error for error in errors):
        return False
    return result.get("action_id") is None and result.get("agent_run_id") is None


@router.get("/bad-debts/clients/{msisdn}", response_model=BadDebtClientDetail)
def get_bad_debt_client(msisdn: str, service: BadDebtsService = Depends(get_bad_debts_service)):
    client = service.get_client(msisdn)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Client introuvable : {msisdn}",
        )
    return client


@router.get("/bad-debts/import-runs", response_model=list[ImportRunItem])
def list_bad_debt_import_runs(
    limit: int = Query(default=20, ge=1, le=100),
    service: BadDebtsService = Depends(get_bad_debts_service),
):
    return service.get_import_runs(limit=limit)
