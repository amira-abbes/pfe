import csv
import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, Response

from app.api.deps import get_current_user, get_user_permissions
from app.core.constants import ROLE_SUPER_ADMIN
from app.models.utilisateur import Utilisateur
from app.services.elt_service import (
    build_pdf_report,
    check_connections,
    get_archive_files,
    get_archive_tables,
    get_latest_report,
    get_runtime_run_status,
    get_watch_status,
    read_csv_rows,
    read_txt_report,
    resolve_elt_path,
    start_runtime_run,
    start_local_watch,
    stop_local_watch,
)
from app.services.elt_job_service import (
    get_job,
    get_latest_job,
    start_job,
)


router = APIRouter(prefix="/elt", tags=["ELT"])


def _route_log(message: str) -> None:
    print(message, flush=True)


def require_any_right(*rights: str):
    def checker(current_user: Utilisateur = Depends(get_current_user)) -> Utilisateur:
        if str(current_user.role or "").upper() == ROLE_SUPER_ADMIN:
            return current_user

        permissions = set(get_user_permissions(current_user))
        if not any(right in permissions for right in rights):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"status": "forbidden", "message": "Acces refuse."},
            )

        return current_user

    return checker


require_lancer_elt = require_any_right("lancer_elt")
require_elt_report_access = require_any_right("dashboard_service_sos", "lancer_elt")


@router.post("/jobs/start")
def start_elt_job(user_mode: str = "AUTO", _: Utilisateur = Depends(require_lancer_elt)):
    normalized_mode = (user_mode or "AUTO").strip().upper()
    if normalized_mode == "AUTO":
        response = run_elt_endpoint(user_mode="AUTO", _=_)
    else:
        response = start_runtime_run(user_mode=normalized_mode)
    _route_log(
        "[ELT JOB] start response="
        + json.dumps(response, ensure_ascii=False, default=str)
    )
    return response


@router.get("/jobs/latest")
def latest_elt_job(_: Utilisateur = Depends(require_elt_report_access)):
    return get_latest_job()


@router.get("/jobs/{job_id}")
def elt_job_status(job_id: str, _: Utilisateur = Depends(require_elt_report_access)):
    return get_job(job_id)


@router.post("/run")
def run_elt_endpoint(user_mode: str = "AUTO", _: Utilisateur = Depends(require_lancer_elt)):
    try:
        normalized_mode = (user_mode or "AUTO").strip().upper()
        _route_log(f"[ELT API] route /elt/run called user_mode={normalized_mode}")
        if normalized_mode == "AUTO":
            connections = check_connections()
            if not connections.get("oracle_ok"):
                response = {
                    **connections,
                    "success": False,
                    "status": "BLOCKED",
                    "message": "Impossible de lancer le traitement. Oracle est indisponible.",
                }
            elif connections.get("ftp_ok"):
                response = {
                    **connections,
                    "success": True,
                    "requires_choice": True,
                    "message": "FTP disponible. Choisissez le mode de traitement.",
                    "choices": [
                        {
                            "user_mode": "FTP_DIRECT",
                            "label": "Traitement direct depuis FTP",
                            "description": "Traite directement les fichiers présents sur le serveur FTP sans copie locale.",
                        },
                        {
                            "user_mode": "FTP_TO_LOCAL",
                            "label": "Récupération FTP puis traitement local",
                            "description": "Récupère les fichiers depuis FTP vers le dossier local puis lance le traitement.",
                        },
                    ],
                }
            else:
                response = start_runtime_run(user_mode="LOCAL_ONLY")
        else:
            response = start_runtime_run(user_mode=normalized_mode)
        _route_log(
            "[ELT API] route /elt/run final response="
            + json.dumps(response, ensure_ascii=False, default=str)
        )
        return response
    except ModuleNotFoundError as exc:
        _route_log(f"[ELT API] route /elt/run ModuleNotFoundError={exc.name}")
        raise HTTPException(
            status_code=500,
            detail=f"Dependance Python manquante pour lancer l'ELT : {exc.name}",
        ) from exc
    except Exception as exc:
        _route_log(f"[ELT API] route /elt/run exception={exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/run/start")
def start_run_endpoint(user_mode: str, _: Utilisateur = Depends(require_lancer_elt)):
    _route_log(f"[API] /elt/run/start user_mode={user_mode}")
    return start_runtime_run(user_mode=user_mode)


@router.get("/run/status")
def run_status(_: Utilisateur = Depends(require_elt_report_access)):
    return get_runtime_run_status()


@router.get("/check-connections")
def elt_check_connections(_: Utilisateur = Depends(require_lancer_elt)):
    return check_connections()


@router.post("/watch/start")
def start_watch(_: Utilisateur = Depends(require_lancer_elt)):
    try:
        current_run = get_runtime_run_status()
        if current_run.get("active") or current_run.get("status") in {"RUNNING", "INITIALIZING"}:
            return {
                "success": False,
                "status": "RUNNING",
                "message": "Un traitement ELT est déjà en cours. Veuillez attendre la fin.",
            }
        _route_log("[ELT WATCH] start route called")
        response = start_local_watch()
        _route_log(
            "[ELT WATCH] start route response="
            + json.dumps(response, ensure_ascii=False, default=str)
        )
        return response
    except Exception as exc:
        _route_log(f"[ELT WATCH] start route exception={exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/watch/stop")
def stop_watch(_: Utilisateur = Depends(require_lancer_elt)):
    try:
        _route_log("[ELT WATCH] stop route called")
        response = stop_local_watch()
        _route_log(
            "[ELT WATCH] stop route response="
            + json.dumps(response, ensure_ascii=False, default=str)
        )
        return response
    except Exception as exc:
        _route_log(f"[ELT WATCH] stop route exception={exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/watch/status")
def watch_status(_: Utilisateur = Depends(require_lancer_elt)):
    try:
        _route_log("[ELT WATCH] status route called")
        response = get_watch_status()
        _route_log(
            "[ELT WATCH] status route response="
            + json.dumps(response, ensure_ascii=False, default=str)
        )
        return response
    except Exception as exc:
        _route_log(f"[ELT WATCH] status route exception={exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/latest")
def latest_report(_: Utilisateur = Depends(require_elt_report_access)):
    report = get_latest_report()

    if not report:
        raise HTTPException(status_code=404, detail="Aucun rapport genere.")

    return report


@router.get("/latest-report")
def latest_report_preferred(_: Utilisateur = Depends(require_elt_report_access)):
    report = get_latest_report()

    if not report:
        return {
            "success": False,
            "message": "Aucun rapport généré.",
            "report": None,
        }

    report["success"] = True
    return report


@router.get("/archive-tables")
def archive_tables(limit: int = 20, _: Utilisateur = Depends(require_elt_report_access)):
    _route_log(f"[ELT ARCHIVE] route called limit={limit}")
    response = get_archive_tables(limit=limit)
    _route_log(
        "[ELT ARCHIVE] route response="
        + json.dumps(response, ensure_ascii=False, default=str)
    )
    return response


@router.get("/archive-files")
def archive_files(limit: int = 50, _: Utilisateur = Depends(require_elt_report_access)):
    _route_log(f"[ELT ARCHIVE FILES] route called limit={limit}")
    response = get_archive_files(limit=limit)
    _route_log(
        "[ELT ARCHIVE FILES] route response="
        + json.dumps(response, ensure_ascii=False, default=str)
    )
    return response


@router.get("/archive/adv")
def archive_adv(limit: int = 20, _: Utilisateur = Depends(require_elt_report_access)):
    response = get_archive_tables(limit=limit)
    return {
        "success": response.get("success", False),
        "message": response.get("message", ""),
        "archive_adv": response.get("archive_adv", []),
        "error": response.get("archive_adv_error") or response.get("error"),
    }


@router.get("/archive/rev")
def archive_rev(limit: int = 20, _: Utilisateur = Depends(require_elt_report_access)):
    response = get_archive_tables(limit=limit)
    return {
        "success": response.get("success", False),
        "message": response.get("message", ""),
        "archive_rev": response.get("archive_rev", []),
        "error": response.get("archive_rev_error") or response.get("error"),
    }


@router.get("/csv-data")
def csv_data(path: str, _: Utilisateur = Depends(require_elt_report_access)):
    try:
        return read_csv_rows(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/txt-report")
def txt_report(path: str, _: Utilisateur = Depends(require_elt_report_access)):
    try:
        return read_txt_report(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/download/csv")
def download_csv(path: str, _: Utilisateur = Depends(require_elt_report_access)):
    try:
        csv_path = resolve_elt_path(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not csv_path.exists():
        raise HTTPException(status_code=404, detail=f"CSV introuvable : {csv_path}")

    return FileResponse(
        str(csv_path),
        filename=csv_path.name,
        media_type="text/csv",
    )


@router.get("/download/txt")
def download_txt(path: str, _: Utilisateur = Depends(require_elt_report_access)):
    try:
        txt_path = resolve_elt_path(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not txt_path.exists():
        raise HTTPException(status_code=404, detail=f"TXT introuvable : {txt_path}")

    try:
        content = read_txt_report(path).get("content", "")
        headers = {"Content-Disposition": f'attachment; filename="{txt_path.name}"'}
        return Response(content=content, media_type="text/plain; charset=utf-8", headers=headers)
    except Exception:
        return FileResponse(
            str(txt_path),
            filename=txt_path.name,
            media_type="text/plain",
        )


@router.get("/download/pdf")
def download_pdf(path: str | None = None, _: Utilisateur = Depends(require_elt_report_access)):
    try:
        content, filename = build_pdf_report(path=path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Generation PDF impossible : {exc}") from exc

    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content=content, media_type="application/pdf", headers=headers)
