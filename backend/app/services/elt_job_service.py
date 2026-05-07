import json
import threading
import traceback
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from app.core.elt_config import ELT_LIVE_STATUS_FILE
from app.services.elt_service import (
    _ftp_choices,
    _normalize_result_paths,
    _test_elt_connections,
    get_latest_report,
    get_watch_status,
    run_elt,
)

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.RLock()
CURRENT_JOB_ID: str | None = None
LATEST_JOB_ID: str | None = None

TERMINAL_STATUSES = {"COMPLETED", "FAILED", "NO_DATA", "STOPPED", "BLOCKED"}
VALID_JOB_MODES = {"AUTO", "FTP_DIRECT", "FTP_TO_LOCAL", "LOCAL_ONLY"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _copy_job(job: dict | None) -> dict | None:
    return deepcopy(job) if job else None


def _is_terminal(status: str | None) -> bool:
    return str(status or "").upper() in TERMINAL_STATUSES


def is_job_running() -> bool:
    with JOBS_LOCK:
        if not CURRENT_JOB_ID:
            return False
        job = JOBS.get(CURRENT_JOB_ID)
        return bool(job and not _is_terminal(job.get("status")))


def _write_live_status(job: dict) -> None:
    try:
        ELT_LIVE_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "job_id": job.get("job_id"),
            "run_id": job.get("run_id"),
            "status": job.get("status"),
            "current_task": job.get("current_step"),
            "progress_percent": job.get("progress_percent", 0),
            "oracle_ok": job.get("oracle_ok"),
            "ftp_ok": job.get("ftp_ok"),
            "scenario": job.get("scenario"),
            "user_mode": job.get("user_mode"),
            "tasks": job.get("tasks", []),
            "message": job.get("message"),
            "updated_at": _now_iso(),
        }
        with open(ELT_LIVE_STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        print(f"[ELT JOB] live_status write skipped: {exc}", flush=True)


def _new_job(user_mode: str, oracle_ok: bool | None = None, ftp_ok: bool | None = None) -> dict:
    job_id = str(uuid4())
    return {
        "job_id": job_id,
        "status": "PENDING",
        "user_mode": user_mode,
        "scenario": None,
        "run_id": None,
        "started_at": None,
        "finished_at": None,
        "progress_percent": 0,
        "current_step": "En attente",
        "message": "Traitement ELT en attente de demarrage.",
        "result": None,
        "error": None,
        "oracle_ok": oracle_ok,
        "ftp_ok": ftp_ok,
        "tasks": [],
    }


def _set_job(job_id: str, **updates) -> dict | None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return None
        job.update(updates)
        _write_live_status(job)
        return _copy_job(job)


def _result_tasks(result: dict | None) -> list[dict]:
    if not isinstance(result, dict):
        return []
    tasks = result.get("tasks")
    if isinstance(tasks, list):
        return tasks
    return []


def _run_job(job_id: str) -> None:
    global CURRENT_JOB_ID

    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return
        job.update(
            {
                "status": "RUNNING",
                "started_at": _now_iso(),
                "progress_percent": 8,
                "current_step": "Demarrage du pipeline ELT",
                "message": "Traitement ELT en cours.",
            }
        )
        _write_live_status(job)

    try:
        result = run_elt(user_mode=job["user_mode"])
        result = _normalize_result_paths(result) if isinstance(result, dict) else result
        if isinstance(result, dict) and result.get("already_running"):
            _set_job(
                job_id,
                status="FAILED",
                result=result,
                finished_at=_now_iso(),
                progress_percent=100,
                current_step="Traitement deja en cours",
                message=result.get("message", "Un traitement ELT est deja en cours."),
                error=result.get("message"),
            )
            return

        status = str(result.get("status") if isinstance(result, dict) else "FAILED").upper()
        if status == "SUCCESS":
            status = "COMPLETED"
        if status not in TERMINAL_STATUSES:
            status = "COMPLETED" if result and not result.get("error") else "FAILED"

        _set_job(
            job_id,
            status=status,
            scenario=result.get("scenario") if isinstance(result, dict) else None,
            run_id=result.get("run_id") if isinstance(result, dict) else None,
            result=result,
            tasks=_result_tasks(result),
            finished_at=_now_iso(),
            progress_percent=100,
            current_step="Rapport genere",
            message=result.get("message") if isinstance(result, dict) and result.get("message") else "Traitement ELT termine.",
            error=result.get("error") if isinstance(result, dict) else None,
        )
    except Exception as exc:
        _set_job(
            job_id,
            status="FAILED",
            finished_at=_now_iso(),
            progress_percent=100,
            current_step="Erreur",
            message="Erreur lors du traitement ELT.",
            error=f"{exc}\n{traceback.format_exc()}",
        )
    finally:
        with JOBS_LOCK:
            if CURRENT_JOB_ID == job_id:
                CURRENT_JOB_ID = None


def start_job(user_mode: str = "AUTO") -> dict:
    global CURRENT_JOB_ID, LATEST_JOB_ID

    user_mode = (user_mode or "AUTO").strip().upper()
    if user_mode not in VALID_JOB_MODES:
        return {
            "success": False,
            "status": "INVALID_MODE",
            "message": f"Mode ELT invalide : {user_mode}.",
        }

    with JOBS_LOCK:
        if CURRENT_JOB_ID and not _is_terminal(JOBS.get(CURRENT_JOB_ID, {}).get("status")):
            return {
                "success": False,
                "already_running": True,
                "status": "RUNNING",
                "message": "Un traitement ELT est deja en cours. Veuillez attendre la fin.",
                "job_id": CURRENT_JOB_ID,
            }

    watch = get_watch_status()
    if watch.get("watching"):
        return {
            "success": False,
            "watch_active": True,
            "status": "WATCH_RUNNING",
            "message": "Pour lancer l'ELT, desactivez d'abord la surveillance locale.",
        }

    try:
        oracle_ok, ftp_ok = _test_elt_connections()
    except Exception as exc:
        return {
            "success": False,
            "status": "FAILED",
            "oracle_ok": False,
            "ftp_ok": False,
            "message": f"Impossible de tester Oracle/FTP : {exc}",
            "error": str(exc),
        }

    if not oracle_ok:
        return {
            "success": False,
            "status": "BLOCKED",
            "oracle_ok": False,
            "ftp_ok": ftp_ok,
            "message": "Oracle indisponible, traitement impossible.",
        }

    if user_mode == "AUTO" and ftp_ok:
        return {
            "success": True,
            "requires_choice": True,
            "oracle_ok": True,
            "ftp_ok": True,
            "message": "FTP disponible. Choisissez le mode de traitement.",
            "choices": _ftp_choices(),
        }

    effective_mode = "LOCAL_ONLY" if user_mode == "AUTO" and not ftp_ok else user_mode

    if effective_mode in {"FTP_DIRECT", "FTP_TO_LOCAL"} and not ftp_ok:
        return {
            "success": False,
            "status": "BLOCKED",
            "oracle_ok": True,
            "ftp_ok": False,
            "message": "FTP indisponible. Choisissez le traitement local ou retestez la connexion.",
        }

    job = _new_job(effective_mode, oracle_ok=oracle_ok, ftp_ok=ftp_ok)
    with JOBS_LOCK:
        JOBS[job["job_id"]] = job
        CURRENT_JOB_ID = job["job_id"]
        LATEST_JOB_ID = job["job_id"]
        _write_live_status(job)

    thread = threading.Thread(target=_run_job, args=(job["job_id"],), daemon=True)
    thread.start()

    return {
        "success": True,
        "job_id": job["job_id"],
        "status": job["status"],
        "user_mode": effective_mode,
        "oracle_ok": oracle_ok,
        "ftp_ok": ftp_ok,
        "message": "Traitement ELT demarre en arriere-plan.",
    }


def get_job(job_id: str) -> dict:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return {
                "success": False,
                "status": "NOT_FOUND",
                "message": "Job ELT introuvable.",
            }
        return {"success": True, **_copy_job(job)}


def get_latest_job() -> dict:
    with JOBS_LOCK:
        if LATEST_JOB_ID and LATEST_JOB_ID in JOBS:
            return {"success": True, **_copy_job(JOBS[LATEST_JOB_ID])}

    latest_report = get_latest_report()
    if latest_report:
        return {
            "success": True,
            "status": latest_report.get("status", "COMPLETED"),
            "message": "Dernier rapport ELT disponible.",
            "result": latest_report,
            "run_id": latest_report.get("run_id"),
            "scenario": latest_report.get("scenario"),
            "user_mode": latest_report.get("user_mode"),
        }

    return {
        "success": False,
        "status": "NOT_FOUND",
        "message": "Aucun job ELT connu.",
    }
