from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.schemas.security import (
    ReportSuspiciousActivityRequest,
    ReportSuspiciousActivityResponse,
)
from app.services.security_incident_service import SecurityIncidentService

router = APIRouter(prefix="/auth/security", tags=["Sécurité"])


def get_client_context(request: Request):
    adresse_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return adresse_ip, user_agent


def get_security_incident_service(
    db: Session = Depends(get_db),
) -> SecurityIncidentService:
    return SecurityIncidentService(db)


@router.post(
    "/report-suspicious",
    response_model=ReportSuspiciousActivityResponse,
)
def report_suspicious_activity(
    payload: ReportSuspiciousActivityRequest,
    request: Request,
    service: SecurityIncidentService = Depends(get_security_incident_service),
):
    adresse_ip, user_agent = get_client_context(request)

    return service.report_suspicious_activity(
        report_token=payload.report_token,
        adresse_ip=adresse_ip,
        user_agent=user_agent,
    )


@router.post(
    "/admin-report",
    response_model=ReportSuspiciousActivityResponse,
)
def confirm_admin_security_report(
    payload: ReportSuspiciousActivityRequest,
    request: Request,
    service: SecurityIncidentService = Depends(get_security_incident_service),
):
    adresse_ip, user_agent = get_client_context(request)

    return service.confirm_admin_security_report(
        report_token=payload.report_token,
        adresse_ip=adresse_ip,
        user_agent=user_agent,
    )


@router.post(
    "/admin-report/status",
    response_model=ReportSuspiciousActivityResponse,
)
def get_admin_security_report_status(
    payload: ReportSuspiciousActivityRequest,
    service: SecurityIncidentService = Depends(get_security_incident_service),
):
    return service.get_admin_security_report_status(report_token=payload.report_token)


@router.get("/report-suspicious-link")
def report_suspicious_activity_from_email(
    request: Request,
    token: str | None = None,
    service: SecurityIncidentService = Depends(get_security_incident_service),
):
    adresse_ip, user_agent = get_client_context(request)
    frontend_base_url = settings.FRONTEND_BASE_URL.rstrip("/")

    if not token:
        return RedirectResponse(
            url=f"{frontend_base_url}/security/incident-report?status=invalid",
            status_code=302,
        )

    try:
        result = service.report_suspicious_activity(
            report_token=token,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
        )

        status_value = result.get("status") or "success"
        return RedirectResponse(
            url=f"{frontend_base_url}/security/incident-report?status={status_value}",
            status_code=302,
        )

    except HTTPException as exc:
        target_status = "invalid" if exc.status_code in [400, 401, 403, 404] else "error"
        return RedirectResponse(
            url=f"{frontend_base_url}/security/incident-report?status={target_status}",
            status_code=302,
        )

    except Exception:
        return RedirectResponse(
            url=f"{frontend_base_url}/security/incident-report?status=error",
            status_code=302,
        )
