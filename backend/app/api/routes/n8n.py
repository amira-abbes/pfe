from fastapi import APIRouter, Depends, HTTPException, Query, Security, status
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.services.bad_debts_service import BadDebtsService


router = APIRouter(prefix="/api/v1/n8n", tags=["n8n Internal"])

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _require_n8n_key(key: str | None = Security(_api_key_header)) -> None:
    expected = settings.N8N_API_KEY
    if not expected or not key or key != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing X-API-Key.",
        )


def _get_service(db: Session = Depends(get_db)) -> BadDebtsService:
    return BadDebtsService(db)


@router.get("/metrics/summary")
def n8n_metrics_summary(
    _: None = Depends(_require_n8n_key),
    service: BadDebtsService = Depends(_get_service),
):
    return service.get_summary()


@router.get("/clients/at-risk")
def n8n_clients_at_risk(
    tier: str = Query(default="high"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    _: None = Depends(_require_n8n_key),
    service: BadDebtsService = Depends(_get_service),
):
    return service.list_at_risk_clients(tier=tier, page=page, page_size=page_size)


@router.get("/agent/reports")
def n8n_agent_reports(
    limit: int = Query(default=1, ge=1, le=10),
    _: None = Depends(_require_n8n_key),
    service: BadDebtsService = Depends(_get_service),
):
    """Returns a digest of the current metrics formatted as an agentic report summary."""
    summary = service.get_summary()
    by_tier = summary.get("by_tier", {})
    high = by_tier.get("high", 0)
    medium = by_tier.get("medium", 0)
    total = summary.get("total_clients", 0)
    anomalies = summary.get("anomaly_count", 0)
    avg_score = summary.get("avg_final_risk_score")

    report = {
        "summary": (
            f"Portefeuille Bad Debts : {total} clients scorés. "
            f"{high} à risque élevé, {medium} à risque moyen, "
            f"{anomalies} anomalies détectées. "
            f"Score moyen : {round(avg_score, 3) if avg_score else 'N/A'}."
        ),
        "recommendations": (
            "Prioriser le traitement des clients à risque élevé. "
            "Vérifier les anomalies détectées par le modèle ML. "
            "Consulter le dashboard pour les détails par segment."
        ),
        "kpis_json": {
            "total_clients": total,
            "at_risk_count": summary.get("at_risk_count", 0),
            "high_risk_count": high,
            "medium_risk_count": medium,
            "anomaly_count": anomalies,
            "avg_final_risk_score": avg_score,
            "latest_import_at": str(summary.get("latest_import_at", "")),
        },
        "generated_at": summary.get("date"),
    }
    return [report]
