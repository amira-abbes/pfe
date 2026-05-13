from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.bad_debts import (
    AgentActionItem,
    BadDebtClientDetail,
    BadDebtClientsPage,
    BadDebtsAgentBatchResponse,
    BadDebtsAgentReportItem,
    BadDebtsHealthResponse,
    BadDebtsSummary,
    BadDebtsAgentResponse,
    ImportRunItem,
    N8nAtRiskClientsPage,
    N8nSummary,
)
from app.services.bad_debts_agent_service import (
    AgentRunError,
    get_recent_agent_actions,
    get_recent_agent_reports,
    run_bad_debts_agent,
    run_bad_debts_agent_batch,
)
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
    search: str | None = Query(default=None),
    service: BadDebtsService = Depends(get_bad_debts_service),
):
    return service.list_clients(
        page=page,
        page_size=page_size,
        risk_tier=risk_tier,
        cluster_name=cluster_name,
        is_anomaly=is_anomaly,
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


@router.get("/bad-debts/actions/recent", response_model=list[AgentActionItem])
def list_recent_bad_debt_agent_actions(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return get_recent_agent_actions(db, limit=limit)


@router.post("/bad-debts/clients/{msisdn}/run-agent", response_model=BadDebtsAgentResponse)
def run_bad_debt_agent(msisdn: str, db: Session = Depends(get_db)):
    try:
        response = run_bad_debts_agent(db, msisdn)
    except AgentRunError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    if not response:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Client introuvable : {msisdn}",
        )
    return response


@router.post("/bad-debts/agent/run-batch", response_model=BadDebtsAgentBatchResponse)
def run_bad_debt_agent_batch(
    tier: str = Query(default="high"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return run_bad_debts_agent_batch(db, tier=tier, limit=limit)


@router.get("/bad-debts/agent/reports", response_model=list[BadDebtsAgentReportItem])
def list_bad_debt_agent_reports(
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    return get_recent_agent_reports(db, limit=limit)


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


@router.get("/metrics/summary", response_model=N8nSummary, tags=["Bad Debts ML - n8n aliases"])
def n8n_metrics_summary(service: BadDebtsService = Depends(get_bad_debts_service)):
    # TODO: add an API-key dependency here before exposing n8n aliases outside local/internal networks.
    return service.get_n8n_summary()


@router.get("/clients/at-risk", response_model=N8nAtRiskClientsPage, tags=["Bad Debts ML - n8n aliases"])
def n8n_at_risk_clients(
    tier: str = Query(default="high"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    service: BadDebtsService = Depends(get_bad_debts_service),
):
    # TODO: add an API-key dependency here before exposing n8n aliases outside local/internal networks.
    return service.get_n8n_at_risk_clients(tier=tier, page=page, page_size=page_size)
