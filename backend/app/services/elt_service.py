import csv
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
import json
import logging
import os
import subprocess
import sys
import threading
import traceback
from importlib import import_module
from pathlib import Path
from typing import Any

from app.core.elt_config import (
    ELT_CURRENT_RUN_STATUS_FILE,
    ELT_LATEST_REPORT_FILE,
    ELT_MAIN_FILE,
    ELT_PYTHON_EXE,
    ELT_PROJECT_DIR,
    ELT_WATCH_FILE,
    ELT_WATCH_PROCESS_FILE,
    ELT_WATCHER_STATUS_FILE,
    TT_LOGO_FILE,
)

ELT_RUN_LOCK = threading.Lock()
FALLBACK_RUN_STATE: dict[str, Any] = {
    "active": False,
    "status": "STOPPED",
    "message": "Aucun traitement ELT actif pour le moment.",
}
FALLBACK_RUN_STATE_LOCK = threading.Lock()

MANUAL_RUN_MODES = {"FTP_DIRECT", "FTP_TO_LOCAL", "LOCAL_ONLY"}
FINAL_RUN_STATUSES = {"COMPLETED", "NO_DATA", "FAILED", "PARTIAL_FAILURE", "STOPPED"}

SCENARIO_LABELS = {
    "FTP_DIRECT": "Traitement direct depuis FTP",
    "FTP_TO_LOCAL": "Récupération FTP puis traitement local",
    "LOCAL_ONLY": "Traitement local manuel",
    "LOCAL_FALLBACK": "Traitement local",
    "STOP": "Traitement arrêté",
}

STATUS_LABELS = {
    "COMPLETED": "Traitement terminé avec succès",
    "NO_DATA": "Aucune donnée à traiter",
    "FAILED": "Traitement échoué",
    "PARTIAL_FAILURE": "Traitement partiellement réussi",
    "STOPPED": "Traitement arrêté",
    "RUNNING": "Traitement en cours",
    "INITIALIZING": "Initialisation",
}

TECHNICAL_TASK_COLUMNS = [
    "task_name",
    "task_label",
    "table_label",
    "branch",
    "status",
    "start_time",
    "end_time",
    "duration_sec",
    "retry_count",
    "fallback_used",
    "fallback_script",
    "error_message",
]

REPORT_DISPLAY_NAME = "Service SOS Solde & Data"

ARCHIVE_ADV_COLUMNS = [
    "NOM_FICHIER",
    "DATE_AJOUT",
    "DATE_FICHIER",
    "NB_LIGNES_FICHIER",
    "NB_LIGNES_INSERE",
    "NB_LIGNES_ERREUR",
    "LOAD_OK",
    "DETAIL_OK",
    "AGG_OK",
    "SERVICE",
    "PARC_OK",
    "ARCHIVE_PARQUET",
    "LOAD_STATUS",
]

ARCHIVE_REV_COLUMNS = [
    "NOM_FICHIER",
    "DATE_AJOUT",
    "DATE_FICHIER",
    "NB_LIGNES_FICHIER",
    "NB_LIGNES_INSERE",
    "NB_LIGNES_ERREUR",
    "LOAD_OK",
    "DETAIL_OK",
    "AGG_OK",
    "SERVICE",
    "ARCHIVE_PARQUET",
    "LOAD_STATUS",
]


def _archive_columns_for(table_name: str) -> list[str]:
    return ARCHIVE_REV_COLUMNS if table_name.upper() == "ARCHIVE_REV_TMP" else ARCHIVE_ADV_COLUMNS


def _log(message: str) -> None:
    print(message, flush=True)


def _log_response(prefix: str, response: dict[str, Any]) -> None:
    if not isinstance(response, dict):
        _log(f"{prefix} success=false")
        return
    parts = [
        f"success={response.get('success')}",
        f"status={response.get('status') or response.get('state')}",
        f"active={response.get('active')}",
        f"run_id={response.get('run_id')}",
    ]
    _log(f"{prefix} " + " ".join(part for part in parts if not part.endswith("=None")))


def _normalize_result_paths(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("csv_report_path") and not result.get("csv_path"):
        result["csv_path"] = result["csv_report_path"]
    if result.get("technical_tasks_csv_path") and not result.get("csv_path"):
        result["csv_path"] = result["technical_tasks_csv_path"]
    if result.get("txt_report_path") and not result.get("txt_path"):
        result["txt_path"] = result["txt_report_path"]
    if result.get("scenario"):
        result["scenario_label"] = _scenario_label(result.get("scenario"))
    if result.get("status"):
        result["status_label"] = _status_label(result.get("status"))
    return result


def _validate_elt_project() -> None:
    _log(f"[ELT API] ELT_PROJECT_DIR={ELT_PROJECT_DIR}")
    if not ELT_PROJECT_DIR.exists():
        raise FileNotFoundError(f"Dossier ELT introuvable : {ELT_PROJECT_DIR}")
    if not ELT_MAIN_FILE.exists():
        raise FileNotFoundError(f"Fichier orchestrateur introuvable : {ELT_MAIN_FILE}")
    if not ELT_WATCH_FILE.exists():
        raise FileNotFoundError(f"Fichier de surveillance introuvable : {ELT_WATCH_FILE}")


def _ensure_elt_on_path() -> None:
    elt_path = str(ELT_PROJECT_DIR)
    if elt_path not in sys.path:
        sys.path.insert(0, elt_path)


def _scenario_label(value: str | None) -> str:
    normalized = str(value or "").upper()
    return SCENARIO_LABELS.get(normalized, value or "-")


def _status_label(value: str | None) -> str:
    normalized = str(value or "").upper()
    return STATUS_LABELS.get(normalized, value or "Non renseigné")


def _read_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _runtime_call(function_name: str, *args):
    _validate_elt_project()
    _ensure_elt_on_path()

    old_cwd = os.getcwd()
    restore_cwd = function_name != "start_run"
    try:
        os.chdir(ELT_PROJECT_DIR)
        root_logger = logging.getLogger()
        if not root_logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s", "%H:%M:%S"))
            root_logger.addHandler(handler)
            root_logger.setLevel(logging.INFO)
        try:
            reporting_module = import_module("orchestrator.reporting")
            registry_module = import_module("orchestrator.dynamic_registry_builder")
            if not hasattr(reporting_module, "build_registry_for_scenario"):
                setattr(
                    reporting_module,
                    "build_registry_for_scenario",
                    getattr(registry_module, "build_registry_for_scenario"),
                )
        except Exception as exc:
            _log(f"[RUNTIME] registry compatibility patch skipped: {exc}")
        _log("[RUNTIME] import platform_runtime.elt_run_manager")
        module = import_module("platform_runtime.elt_run_manager")
        try:
            module.STATUS_FILE = ELT_CURRENT_RUN_STATUS_FILE
            module.WATCHER_STATUS_FILE = ELT_WATCHER_STATUS_FILE
        except Exception as exc:
            _log(f"[RUNTIME] absolute status path patch skipped: {exc}")
        return getattr(module, function_name)(*args)
    finally:
        if restore_cwd:
            os.chdir(old_cwd)


def _fallback_is_run_active() -> bool:
    with FALLBACK_RUN_STATE_LOCK:
        return bool(FALLBACK_RUN_STATE.get("active"))


def _write_fallback_run_status(status: dict[str, Any]) -> None:
    try:
        ELT_CURRENT_RUN_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(ELT_CURRENT_RUN_STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(status, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        _log(f"[RUNTIME FALLBACK] current status write skipped: {exc}")


def _fallback_get_current_run_status() -> dict[str, Any]:
    with FALLBACK_RUN_STATE_LOCK:
        fallback_state = dict(FALLBACK_RUN_STATE)

    status = _read_json_file(ELT_CURRENT_RUN_STATUS_FILE, {})
    if isinstance(status, dict) and status:
        if fallback_state.get("active"):
            file_status = str(status.get("status") or "").upper()
            if status.get("active") or file_status not in FINAL_RUN_STATUSES:
                status["active"] = True
                status.setdefault("user_mode", fallback_state.get("user_mode"))
                status.setdefault("scenario_label", fallback_state.get("scenario_label"))
                return status
            return fallback_state
        return status
    return fallback_state


def _fallback_run_worker(user_mode: str) -> None:
    try:
        result = run_elt(user_mode=user_mode)
        normalized = _normalize_result_paths(result if isinstance(result, dict) else {})
        final_status = str(normalized.get("status") or "FAILED").upper()
        with FALLBACK_RUN_STATE_LOCK:
            FALLBACK_RUN_STATE.update({
                "active": False,
                "status": final_status,
                "message": normalized.get("message") or _status_label(final_status),
                "user_mode": user_mode,
                "scenario_label": _scenario_label(normalized.get("scenario") or user_mode),
                "run_id": normalized.get("run_id"),
                "scenario": normalized.get("scenario") or user_mode,
            })
            current_state = dict(FALLBACK_RUN_STATE)
        _write_fallback_run_status(current_state)
    except Exception as exc:
        _log(f"[RUNTIME FALLBACK] worker error={exc}")
        _log(traceback.format_exc())
        with FALLBACK_RUN_STATE_LOCK:
            FALLBACK_RUN_STATE.update({
                "active": False,
                "status": "FAILED",
                "message": f"Erreur lors du traitement ELT : {exc}",
                "user_mode": user_mode,
            })
            current_state = dict(FALLBACK_RUN_STATE)
        _write_fallback_run_status(current_state)


def _fallback_start_run(user_mode: str) -> dict[str, Any]:
    if _fallback_is_run_active():
        return {"success": False, "error": "ALREADY_RUNNING", "message": "Un traitement ELT est déjà en cours."}
    with FALLBACK_RUN_STATE_LOCK:
        FALLBACK_RUN_STATE.update({
            "active": True,
            "status": "INITIALIZING",
            "message": "Initialisation du traitement ELT.",
            "user_mode": user_mode,
            "scenario_label": _scenario_label(user_mode),
        })
        current_state = dict(FALLBACK_RUN_STATE)
    _write_fallback_run_status(current_state)
    thread = threading.Thread(target=_fallback_run_worker, args=(user_mode,), daemon=True)
    thread.start()
    return {"success": True, "status": "RUNNING", "message": "Traitement lancé."}


def _normalize_run_status(status: dict[str, Any] | None) -> dict[str, Any]:
    data = dict(status or {})
    active = bool(data.get("active"))
    raw_status = data.get("status") or data.get("global_status")

    if not raw_status:
        raw_status = "RUNNING" if active else "STOPPED"
    raw_status = str(raw_status).upper()

    if active and raw_status not in FINAL_RUN_STATUSES:
        display_status = "RUNNING" if raw_status not in {"INITIALIZING"} else raw_status
    else:
        display_status = raw_status

    data["success"] = True
    data["active"] = active
    data["status"] = display_status
    data["status_label"] = data.get("status_label") or data.get("global_status_label") or _status_label(display_status)
    data["scenario_label"] = _scenario_label(data.get("scenario") or data.get("user_mode"))
    data["oracle_label"] = "Oracle connecté" if data.get("oracle_ok") is True else "Oracle indisponible"
    data["ftp_label"] = "FTP connecté" if data.get("ftp_ok") is True else "FTP indisponible"
    data["message"] = data.get("message") or data.get("global_status_description") or data["status_label"]
    data.setdefault("global_progress_percent", 100 if display_status in FINAL_RUN_STATUSES else 0)
    data.setdefault("adv_progress_percent", 0)
    data.setdefault("rev_progress_percent", 0)
    data.setdefault("completed_count", 0)
    data.setdefault("running_count", 0)
    data.setdefault("waiting_count", 0)
    data.setdefault("failed_count", 0)
    return data


def _is_watcher_process_alive() -> bool:
    process_data = _read_json_file(ELT_WATCH_PROCESS_FILE, {})
    pid = process_data.get("pid") if isinstance(process_data, dict) else None
    if not pid:
        return False
    if not _pid_matches_watcher(pid):
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False
    except Exception:
        return False


def _pid_matches_watcher(pid: Any) -> bool:
    try:
        pid_int = int(pid)
    except Exception:
        return False

    if os.name != "nt":
        stored = _read_json_file(ELT_WATCH_PROCESS_FILE, {})
        command = " ".join(str(part) for part in stored.get("command", [])) if isinstance(stored, dict) else ""
        return ELT_WATCH_FILE.name.lower() in command.lower()

    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"$p=Get-CimInstance Win32_Process -Filter \"ProcessId={pid_int}\"; if ($p) {{ $p.CommandLine }}",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        command_line = (result.stdout or "").lower()
        expected_script = str(ELT_WATCH_FILE).lower()
        return expected_script in command_line and "uvicorn" not in command_line
    except Exception as exc:
        _log(f"[WATCH] unable to verify pid command line: {exc}")
        return False


def _is_manual_watcher_active() -> bool:
    status = _read_json_file(ELT_WATCHER_STATUS_FILE, {})
    state = str(status.get("state") or "").upper() if isinstance(status, dict) else ""
    if state in {"", "STOPPED"}:
        return _is_watcher_process_alive()
    state_active = state in {
        "WAITING_FOR_FILE",
        "FILE_STABLE",
        "PROCESSING",
        "ORACLE_KO",
    }
    file_active = bool(isinstance(status, dict) and (status.get("active") or status.get("watching")))
    return _is_watcher_process_alive() or file_active or state_active


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def import_elt_main():
    """
    Import main_orchestrator.py from the external PyCharm ELT project.
    """
    _validate_elt_project()
    _ensure_elt_on_path()

    old_cwd = os.getcwd()
    try:
        os.chdir(ELT_PROJECT_DIR)
        module = import_module("main_orchestrator")
        module_file = Path(getattr(module, "__file__", "")).resolve()
        _log(f"[ELT API] imported ELT main from: {module_file}")
        return getattr(module, "main")
    finally:
        os.chdir(old_cwd)


def _test_elt_connections() -> tuple[bool, bool]:
    _validate_elt_project()
    _ensure_elt_on_path()

    old_cwd = os.getcwd()
    try:
        _log(f"[ELT API] chdir to {ELT_PROJECT_DIR}")
        os.chdir(ELT_PROJECT_DIR)
        from test_conn import test_ftp, test_oracle

        oracle_ok = bool(test_oracle())
        ftp_ok = bool(test_ftp())
        return oracle_ok, ftp_ok
    finally:
        os.chdir(old_cwd)


def check_connections() -> dict[str, Any]:
    try:
        oracle_ok, ftp_ok = _test_elt_connections()
        return {
            "success": True,
            "oracle_ok": oracle_ok,
            "ftp_ok": ftp_ok,
            "oracle_label": "Oracle connecté" if oracle_ok else "Oracle indisponible",
            "ftp_label": "FTP connecté" if ftp_ok else "FTP indisponible",
            "message": "Connexions vérifiées.",
        }
    except Exception as exc:
        _log(f"[ELT CHECK] error={exc}")
        _log(traceback.format_exc())
        return {
            "success": False,
            "oracle_ok": False,
            "ftp_ok": False,
            "oracle_label": "Oracle indisponible",
            "ftp_label": "FTP indisponible",
            "message": "Impossible de vérifier les connexions Oracle et FTP.",
            "error": str(exc),
        }


def start_runtime_run(user_mode: str) -> dict[str, Any]:
    normalized_mode = (user_mode or "").strip().upper()
    _log(f"[SERVICE] start_runtime_run user_mode={normalized_mode}")
    _log(f"[ELT RUN] start requested user_mode={normalized_mode}")
    if normalized_mode not in MANUAL_RUN_MODES:
        return {
            "success": False,
            "status": "INVALID_MODE",
            "message": "Mode de lancement invalide.",
            "valid_modes": sorted(MANUAL_RUN_MODES),
        }

    try:
        try:
            run_active = bool(_runtime_call("is_run_active"))
            runtime_start = lambda: _runtime_call("start_run", normalized_mode)
        except ModuleNotFoundError as exc:
            if exc.name != "platform_runtime":
                raise
            _log("[RUNTIME] platform_runtime absent, fallback thread plateforme utilisé")
            run_active = _fallback_is_run_active()
            runtime_start = lambda: _fallback_start_run(normalized_mode)

        if run_active:
            return {
                "success": False,
                "already_running": True,
                "status": "RUNNING",
                "message": "Un traitement ELT est déjà en cours. Veuillez attendre la fin.",
            }

        watcher = get_watch_status()
        watcher_active = bool(watcher.get("active") or watcher.get("watching") or _is_manual_watcher_active())
        _log(f"[ELT RUN] watcher active={watcher_active} state={watcher.get('state')}")
        if watcher_active:
            return {
                "success": False,
                "watch_active": True,
                "status": "WATCHER_ACTIVE",
                "message": "La surveillance locale est active. Pour lancer un traitement manuel, désactivez d’abord la surveillance.",
            }

        _log("[ELT RUN] start accepted")
        result = runtime_start()
        _log_response("[RUNTIME] start_run result", result)
        if not result.get("success"):
            error_code = result.get("error")
            return {
                "success": False,
                "status": "WATCHER_ACTIVE" if error_code == "WATCHER_ACTIVE_MANUAL_RUN_BLOCKED" else "RUNNING",
                "watch_active": error_code == "WATCHER_ACTIVE_MANUAL_RUN_BLOCKED",
                "already_running": error_code == "ALREADY_RUNNING",
                "message": result.get("message") or "Lancement ELT refusé.",
            }

        return {
            "success": True,
            "status": "RUNNING",
            "message": "Traitement lancé.",
            "user_mode": normalized_mode,
            "scenario_label": _scenario_label(normalized_mode),
        }
    except Exception as exc:
        _log(f"[ELT RUNTIME] start error={exc}")
        _log(traceback.format_exc())
        return {
            "success": False,
            "status": "FAILED",
            "message": "Impossible de lancer le traitement ELT.",
            "error": str(exc),
        }


def get_runtime_run_status() -> dict[str, Any]:
    try:
        status = _runtime_call("get_current_run_status")
        response = _normalize_run_status(status)
        _log_response("[ELT RUN] status response", response)
        return response
    except ModuleNotFoundError as exc:
        if exc.name == "platform_runtime":
            response = _normalize_run_status(_fallback_get_current_run_status())
            _log_response("[ELT RUN] status response", response)
            return response
        raise
    except Exception as exc:
        fallback = _read_json_file(ELT_CURRENT_RUN_STATUS_FILE, None)
        if isinstance(fallback, dict):
            response = _normalize_run_status(fallback)
            _log_response("[ELT RUN] status response", response)
            return response
        response = {
            "success": True,
            "active": False,
            "status": "STOPPED",
            "status_label": _status_label("STOPPED"),
            "message": "Aucun traitement ELT actif pour le moment.",
        }
        _log_response("[ELT RUN] status response", response)
        return response


def _get_elt_oracle_connection():
    _validate_elt_project()
    _ensure_elt_on_path()

    old_cwd = os.getcwd()
    try:
        os.chdir(ELT_PROJECT_DIR)
        from oracle_conn import get_connection

        return get_connection()
    finally:
        os.chdir(old_cwd)


def _existing_columns(conn, table_name: str) -> set[str]:
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT COLUMN_NAME
            FROM USER_TAB_COLUMNS
            WHERE TABLE_NAME = :table_name
            """,
            {"table_name": table_name.upper()},
        )
        return {str(row[0]).upper() for row in cursor.fetchall()}
    finally:
        cursor.close()


def _fetch_archive_rows(conn, table_name: str, limit: int) -> list[dict[str, Any]]:
    existing_columns = _existing_columns(conn, table_name)
    allowed_columns = _archive_columns_for(table_name)
    selected_columns = [column for column in allowed_columns if column in existing_columns]
    if not selected_columns:
        return []

    column_sql = ", ".join(selected_columns)
    order_clause = "ORDER BY DATE_AJOUT DESC" if "DATE_AJOUT" in existing_columns else ""
    query = (
        f"SELECT {column_sql} "
        f"FROM {table_name} "
        f"{order_clause} "
        f"FETCH FIRST {int(limit)} ROWS ONLY"
    )

    cursor = conn.cursor()
    try:
        cursor.execute(query)
        rows = []
        for row in cursor.fetchall():
            item = {column: None for column in allowed_columns}
            item.update(
                {
                    column: _json_value(value)
                    for column, value in zip(selected_columns, row)
                }
            )
            rows.append(item)
        return rows
    finally:
        cursor.close()


def get_archive_tables(limit: int = 20) -> dict[str, Any]:
    limit = max(1, min(int(limit or 20), 50))
    conn = None
    response = {
        "success": True,
        "message": "Tables archives chargees.",
        "archive_adv": [],
        "archive_rev": [],
    }

    try:
        _log("[ELT ARCHIVE] opening Oracle connection through ELT oracle_conn.get_connection")
        conn = _get_elt_oracle_connection()

        try:
            _log("[ELT ARCHIVE] loading ARCHIVE_ADV_TMP")
            response["archive_adv"] = _fetch_archive_rows(conn, "ARCHIVE_ADV_TMP", limit)
        except Exception as exc:
            response["success"] = False
            response["message"] = "ARCHIVE_ADV_TMP indisponible ou vide."
            response["archive_adv"] = []
            response["archive_adv_error"] = str(exc)
            _log(f"[ELT ARCHIVE] ARCHIVE_ADV_TMP error={exc}")

        try:
            _log("[ELT ARCHIVE] loading ARCHIVE_REV_TMP")
            response["archive_rev"] = _fetch_archive_rows(conn, "ARCHIVE_REV_TMP", limit)
        except Exception as exc:
            response["success"] = False
            if response["message"] == "Tables archives chargees.":
                response["message"] = "ARCHIVE_REV_TMP indisponible ou vide."
            response["archive_rev"] = []
            response["archive_rev_error"] = str(exc)
            _log(f"[ELT ARCHIVE] ARCHIVE_REV_TMP error={exc}")

        _log(f"[ELT ARCHIVE] rows adv={len(response['archive_adv'])}")
        _log(f"[ELT ARCHIVE] rows rev={len(response['archive_rev'])}")

        if not response["success"] and not response.get("archive_adv_error") and not response.get("archive_rev_error"):
            response["message"] = "Aucune donnee archive disponible."

        return response
    except Exception as exc:
        _log(f"[ELT ARCHIVE] error={exc}")
        _log(traceback.format_exc())
        return {
            "success": False,
            "message": "Impossible de charger les tables archives.",
            "archive_adv": [],
            "archive_rev": [],
            "error": str(exc),
        }
    finally:
        if conn:
            try:
                conn.close()
            except Exception as exc:
                _log(f"[ELT ARCHIVE] close connection error={exc}")


def _parse_date(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[: len(fmt)], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _flag_label(value: Any, *, no_data_is_not_required: bool = False) -> str:
    normalized = str(value or "").strip().upper()
    if normalized == "Y":
        return "OK"
    if normalized == "N":
        return "Non nécessaire" if no_data_is_not_required else "En attente"
    if normalized == "SUCCESS":
        return "Succès"
    if normalized in {"FAILED", "FAILED_INSERT", "FAILED_CONTROL"}:
        return "Échec"
    if normalized == "NO_DATA":
        return "Non nécessaire"
    if not normalized:
        return "Non renseigné"
    return str(value)


def _result_label(value: Any) -> str:
    normalized = str(value or "").strip().upper()
    if normalized == "SUCCESS":
        return "Succès"
    if normalized in {"FAILED", "FAILED_INSERT", "FAILED_CONTROL"}:
        return "Échec"
    if normalized == "NO_DATA":
        return "Non nécessaire"
    if normalized in {"Y", "COMPLETED"}:
        return "Succès"
    if normalized == "N":
        return "En attente"
    return "Non renseigné" if not normalized else str(value)


def _archive_label(value: Any, file_date: datetime | None, max_date: datetime | None) -> str:
    normalized = str(value or "").strip().upper()
    if normalized == "Y":
        return "OK"
    if normalized == "N":
        if file_date and max_date and file_date >= max_date - timedelta(days=7):
            return "Fichier récent - conservation 7 jours"
        return "En attente"
    if not normalized:
        return "Non renseigné"
    return str(value)


def _safe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _fetch_max_archive_date(conn, table_name: str) -> datetime | None:
    columns = _existing_columns(conn, table_name)
    if "DATE_FICHIER" not in columns:
        return None
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT MAX(DATE_FICHIER) FROM {table_name}")
        row = cursor.fetchone()
        return _parse_date(row[0] if row else None)
    finally:
        cursor.close()


def _to_archive_file(row: dict[str, Any], flux: str, max_file_date: datetime | None) -> dict[str, Any]:
    file_rows = _safe_int(row.get("NB_LIGNES_FICHIER"))
    inserted_rows = _safe_int(row.get("NB_LIGNES_INSERE"))
    rejected_rows = _safe_int(row.get("NB_LIGNES_ERREUR"))
    if rejected_rows is None and file_rows is not None and inserted_rows is not None:
        rejected_rows = max(file_rows - inserted_rows, 0)

    file_date = _parse_date(row.get("DATE_FICHIER"))

    item = {
        "flux": flux,
        "fichier": row.get("NOM_FICHIER") or "-",
        "date_fichier": row.get("DATE_FICHIER"),
        "date_traitement": row.get("DATE_AJOUT"),
        "lignes_fichier": file_rows,
        "lignes_inserees": inserted_rows,
        "lignes_rejetees": rejected_rows,
        "chargement": _flag_label(row.get("LOAD_OK")),
        "detail": _flag_label(row.get("DETAIL_OK")),
        "aggregation": _flag_label(row.get("AGG_OK")),
        "service": _flag_label(row.get("SERVICE")),
        "archivage": _archive_label(row.get("ARCHIVE_PARQUET"), file_date, max_file_date),
    }
    if flux == "Avance":
        item["parc"] = _flag_label(row.get("PARC_OK"))
    return item


def get_archive_files(limit: int = 50) -> dict[str, Any]:
    limit = max(1, min(int(limit or 50), 200))
    conn = None
    try:
        conn = _get_elt_oracle_connection()
        adv_max = _fetch_max_archive_date(conn, "ARCHIVE_ADV_TMP")
        rev_max = _fetch_max_archive_date(conn, "ARCHIVE_REV_TMP")
        adv_rows = _fetch_archive_rows(conn, "ARCHIVE_ADV_TMP", limit)
        rev_rows = _fetch_archive_rows(conn, "ARCHIVE_REV_TMP", limit)

        adv_files = [_to_archive_file(row, "Avance", adv_max) for row in adv_rows]
        rev_files = [_to_archive_file(row, "Remboursement", rev_max) for row in rev_rows]
        files = [*adv_files, *rev_files]
        _log(f"[ARCHIVE] archive files loaded adv={len(adv_files)} rev={len(rev_files)}")

        return {
            "success": True,
            "message": "Suivi des fichiers traités chargé.",
            "files_adv": adv_files[:limit],
            "files_rev": rev_files[:limit],
            "archive_adv": adv_files[:limit],
            "archive_rev": rev_files[:limit],
            "files": files[:limit],
        }
    except Exception as exc:
        _log(f"[ELT ARCHIVE FILES] error={exc}")
        _log(traceback.format_exc())
        return {
            "success": False,
            "message": "Oracle indisponible. Le suivi des fichiers traités est temporairement vide.",
            "files_adv": [],
            "files_rev": [],
            "archive_adv": [],
            "archive_rev": [],
            "files": [],
            "error": str(exc),
        }
    finally:
        if conn:
            try:
                conn.close()
            except Exception as exc:
                _log(f"[ELT ARCHIVE FILES] close connection error={exc}")


def _ftp_choices() -> list[dict[str, str]]:
    return [
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
    ]


def run_elt(user_mode: str = "AUTO"):
    """
    Run the ELT with a selected mode.
    """
    user_mode = (user_mode or "AUTO").strip().upper()
    _log(f"[ELT API] /elt/run called user_mode={user_mode}")
    _log(f"[ELT API] ELT_PROJECT_DIR used={ELT_PROJECT_DIR}")

    valid_modes = {"AUTO", "FTP_DIRECT", "FTP_TO_LOCAL", "LOCAL_ONLY"}
    if user_mode not in valid_modes:
        response = {
            "success": False,
            "status": "INVALID_MODE",
            "message": f"Mode ELT invalide : {user_mode}. Modes valides : {', '.join(sorted(valid_modes))}",
        }
        _log(f"[ELT API] decision=INVALID_MODE response={response}")
        return response

    acquired = ELT_RUN_LOCK.acquire(blocking=False)
    if not acquired:
        response = {
            "success": False,
            "already_running": True,
            "status": "RUNNING",
            "message": "Un traitement ELT est deja en cours. Veuillez attendre la fin.",
        }
        _log_response("[ELT API] decision=ALREADY_RUNNING response", response)
        return response

    _log("[ELT API] lock acquired")

    try:
        oracle_ok, ftp_ok = _test_elt_connections()
        _log(f"[ELT API] oracle_ok={oracle_ok} ftp_ok={ftp_ok}")

        if not oracle_ok:
            response = {
                "success": False,
                "oracle_ok": False,
                "ftp_ok": ftp_ok,
                "status": "BLOCKED",
                "message": "Oracle indisponible, traitement impossible.",
            }
            _log("[ELT API] decision=BLOCKED")
            _log_response("[ELT API] response", response)
            return response

        if user_mode == "AUTO":
            if ftp_ok:
                response = {
                    "success": True,
                    "requires_choice": True,
                    "oracle_ok": True,
                    "ftp_ok": True,
                    "message": "FTP disponible. Choisissez le mode de traitement.",
                    "choices": _ftp_choices(),
                }
                _log("[ELT API] decision=requires_choice")
                _log("[ELT API] FTP available -> returning requires_choice=true")
                _log_response("[ELT API] response", response)
                return response

            user_mode = "LOCAL_ONLY"
            _log("[ELT API] decision=LOCAL_ONLY")
        else:
            _log(f"[ELT API] decision={user_mode}")

        elt_main = import_elt_main()

        old_cwd = os.getcwd()
        try:
            _log(f"[ELT API] chdir to {ELT_PROJECT_DIR}")
            os.chdir(ELT_PROJECT_DIR)
            _log(f"[ELT API] calling ELT main with user_mode={user_mode}")
            result = elt_main(user_mode=user_mode)
        finally:
            os.chdir(old_cwd)

        _log(f"[ELT API] raw ELT result type={type(result).__name__}")
        if not isinstance(result, dict):
            raise RuntimeError("L'ELT n'a pas retourne un dictionnaire de resultat.")

        result = _normalize_result_paths(result)
        _save_latest_report(result)
        _log(f"[ELT API] ELT finished status={result.get('status')}")
        _log_response("[ELT API] response", result)
        _log("[ELT API] response sent")
        return result

    except Exception as exc:
        _log(f"[ELT API] exception={exc}")
        _log(traceback.format_exc())
        response = {
            "success": False,
            "status": "FAILED",
            "message": f"Erreur lors du traitement ELT : {str(exc)}",
            "error": str(exc),
        }
        _log_response("[ELT API] response", response)
        return response
    finally:
        ELT_RUN_LOCK.release()
        _log("[ELT API] lock released")


def start_local_watch():
    """
    Start local_watch_runner.py in the background.
    """
    _log("[WATCH] start requested")
    _validate_elt_project()
    ELT_WATCH_PROCESS_FILE.parent.mkdir(parents=True, exist_ok=True)

    if _is_watcher_process_alive():
        with open(ELT_WATCH_PROCESS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        pid = data.get("pid")
        if pid:
            response = {
                "success": True,
                "status": "ALREADY_RUNNING",
                "message": "La surveillance locale est deja lancee.",
                "pid": pid,
            }
            _log_response("[ELT WATCH] response", response)
            return response

    python_exe = str(ELT_PYTHON_EXE if ELT_PYTHON_EXE.exists() else sys.executable)
    try:
        popen_kwargs: dict[str, Any] = {
            "cwd": str(ELT_PROJECT_DIR),
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
            "close_fds": True,
        }
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            popen_kwargs["startupinfo"] = startupinfo

        process = subprocess.Popen(
            [python_exe, str(ELT_WATCH_FILE)],
            **popen_kwargs,
        )

        with open(ELT_WATCH_PROCESS_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "pid": process.pid,
                    "command": [python_exe, str(ELT_WATCH_FILE)],
                    "started_at": datetime.now().isoformat(),
                },
                f,
                indent=4,
            )
    except Exception as exc:
        _log(f"[WATCH] start error={exc}")
        _log(traceback.format_exc())
        return {
            "success": False,
            "status": "FAILED",
            "message": f"Impossible d'activer la surveillance locale : {exc}",
            "error": str(exc),
        }

    response = {
        "success": True,
        "status": "STARTED",
        "message": "Surveillance locale lancee. Ajoute un fichier dans le dossier surveille.",
        "pid": process.pid,
    }
    _log_response("[ELT WATCH] response", response)
    return response


def _write_watcher_status_stopped() -> None:
    ELT_WATCHER_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    status = {
        "active": False,
        "watching": False,
        "oracle_ok": None,
        "ftp_ok": None,
        "state": "STOPPED",
        "state_label": "Surveillance arrêtée",
        "message": "Surveillance locale arrêtée.",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        with open(ELT_WATCHER_STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(status, f, indent=4, ensure_ascii=False)
    except Exception as exc:
        _log(f"[WATCH] watcher_status stop write skipped: {exc}")


def stop_local_watch():
    """
    Stop local_watch_runner.py.
    """
    _log("[ELT WATCH] stop called")
    if not ELT_WATCH_PROCESS_FILE.exists():
        _write_watcher_status_stopped()
        response = {
            "success": True,
            "status": "NOT_RUNNING",
            "message": "Aucune surveillance locale active.",
        }
        _log_response("[ELT WATCH] status response", response)
        return response

    with open(ELT_WATCH_PROCESS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    pid = data.get("pid")

    if not pid:
        ELT_WATCH_PROCESS_FILE.unlink(missing_ok=True)
        _write_watcher_status_stopped()
        response = {
            "success": True,
            "status": "NOT_RUNNING",
            "message": "PID introuvable.",
        }
        _log_response("[ELT WATCH] status response", response)
        return response

    if not _pid_matches_watcher(pid):
        ELT_WATCH_PROCESS_FILE.unlink(missing_ok=True)
        _write_watcher_status_stopped()
        response = {
            "success": True,
            "status": "NOT_RUNNING",
            "message": "Aucune surveillance locale active.",
        }
        _log(f"[WATCH] stale or unsafe watcher pid ignored pid={pid}")
        _log_response("[ELT WATCH] response", response)
        return response

    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False)
    else:
        subprocess.run(["kill", str(pid)], check=False)

    ELT_WATCH_PROCESS_FILE.unlink(missing_ok=True)
    _write_watcher_status_stopped()

    response = {
        "success": True,
        "status": "STOPPED",
        "message": "Surveillance locale arretee.",
    }
    _log_response("[ELT WATCH] response", response)
    return response


def get_latest_report():
    """
    Read the latest ELT report generated for the platform.
    """
    if not ELT_LATEST_REPORT_FILE.exists():
        return None

    with open(ELT_LATEST_REPORT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        return _normalize_business_report(_normalize_result_paths(data))
    return data


def _flow_file_count(employee: dict[str, Any], key: str) -> int:
    try:
        return int((employee.get("flows") or {}).get(key, {}).get("file_count") or 0)
    except (TypeError, ValueError):
        return 0


def _build_business_conclusion(report: dict[str, Any]) -> str:
    employee = report.get("employee_report") or {}
    status = str(report.get("status") or employee.get("global_status") or "").upper()
    adv_files = _flow_file_count(employee, "adv")
    rev_files = _flow_file_count(employee, "rev")
    diagnostic = employee.get("diagnostic") or {}

    if status == "COMPLETED" and (adv_files > 0 or rev_files > 0):
        return (
            "Le traitement s’est terminé avec succès. Les fichiers Avance et "
            "Remboursement ont été intégrés et les tables cibles ont été mises à jour."
        )
    if status == "COMPLETED":
        return "Le traitement s’est terminé avec succès et les contrôles métier sont cohérents."
    if status == "NO_DATA":
        return "Aucun nouveau fichier source n’a été détecté. Le traitement a été arrêté proprement sans erreur technique."
    if status == "FAILED":
        task = diagnostic.get("task_label") or diagnostic.get("task_name") or employee.get("failure_cause")
        cause = diagnostic.get("cause") or diagnostic.get("reason") or employee.get("failure_cause") or "cause non renseignée"
        suffix = f" Tâche concernée : {task}." if task else ""
        return f"Le traitement a échoué : {cause}.{suffix}"
    if status == "PARTIAL_FAILURE":
        return "Le traitement est partiellement réussi. Certaines tâches nécessitent une vérification."
    return employee.get("final_conclusion") or "Conclusion métier non disponible."


def _normalize_business_report(report: dict[str, Any]) -> dict[str, Any]:
    employee = report.get("employee_report")
    if not isinstance(employee, dict):
        return report

    scenario = report.get("scenario") or employee.get("scenario") or report.get("user_mode")
    scenario_label = _scenario_label(scenario)
    conclusion = _build_business_conclusion(report)

    employee["scenario_label"] = scenario_label
    employee["report_title"] = REPORT_DISPLAY_NAME
    employee["final_conclusion"] = conclusion
    employee["employee_summary"] = conclusion
    report["scenario_label"] = scenario_label
    if report.get("status"):
        report["status_label"] = _status_label(report.get("status"))
    report["employee_report"] = employee
    return report


def _build_clean_txt_report(report: dict[str, Any]) -> str:
    report = _normalize_business_report(dict(report or {}))
    employee = report.get("employee_report") or {}
    flows = employee.get("flows") or {}
    diagnostic = employee.get("diagnostic") or {}

    def flow_lines(key: str) -> list[str]:
        flow = flows.get(key) or {}
        return [
            f"Statut du flux : {flow.get('status') or 'Non renseigné'}",
            f"Nombre de fichiers : {flow.get('file_count', 0)}",
            f"Période des fichiers : {flow.get('min_file_date') or 'Non renseigné'} au {flow.get('max_file_date') or 'Non renseigné'}",
            f"Dernier traitement : {flow.get('last_processing_date') or 'Non renseigné'}",
            f"Lignes fichier : {flow.get('total_file_rows', 0)}",
            f"Lignes insérées : {flow.get('total_inserted_rows', 0)}",
            f"Lignes rejetées : {flow.get('total_error_rows', 0)}",
        ]

    lines = [
        REPORT_DISPLAY_NAME,
        "",
        "Informations générales",
        f"Date de génération : {employee.get('generated_at') or datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Statut global : {_status_label(report.get('status') or employee.get('global_status'))}",
        f"Scénario utilisé : {report.get('scenario_label') or employee.get('scenario_label') or _scenario_label(report.get('scenario'))}",
        f"Oracle : {'Connecté' if report.get('oracle_ok') is True or employee.get('oracle_ok') is True else 'Indisponible'}",
        f"FTP : {'Connecté' if report.get('ftp_ok') is True or employee.get('ftp_ok') is True else 'Indisponible'}",
        "Flux Avance",
        *flow_lines("adv"),
        "",
        "Flux Remboursement",
        *flow_lines("rev"),
    ]

    if diagnostic.get("available") or str(report.get("status") or "").upper() in {"FAILED", "PARTIAL_FAILURE"}:
        lines.extend([
            "",
            "Diagnostic",
            f"Cause : {diagnostic.get('cause') or diagnostic.get('reason') or employee.get('failure_cause') or 'Non renseigné'}",
            f"Action recommandée : {diagnostic.get('recommended_action') or diagnostic.get('final_action') or 'Non renseigné'}",
        ])

    lines.extend([
        "",
        "Conclusion métier",
        "Traitement terminé.",
    ])
    return "\n".join(str(line) for line in lines)


def get_watch_status():
    """
    Check local watcher status.
    """
    _log("[ELT WATCH] status called")
    state_labels = {
        "WAITING_FOR_FILE": "En attente de fichier",
        "FILE_STABLE": "Fichier stable détecté",
        "PROCESSING": "Traitement en cours",
        "ORACLE_KO": "Oracle indisponible",
        "STOPPED": "Surveillance arrêtée",
        "FTP_OK_LOCAL_SKIP": "FTP disponible - traitement local non requis",
        "PROCESSING_ERROR": "Erreur de traitement",
        "STABILIZATION_TIMEOUT": "Fichier non stabilisé",
    }

    try:
        process_alive = _is_watcher_process_alive()
        if ELT_WATCH_PROCESS_FILE.exists() and not process_alive:
            ELT_WATCH_PROCESS_FILE.unlink(missing_ok=True)

        file_status = _read_json_file(ELT_WATCHER_STATUS_FILE, {})
        if not isinstance(file_status, dict):
            file_status = {}

        state = str(file_status.get("state") or ("WAITING_FOR_FILE" if process_alive else "STOPPED")).upper()
        active_states = {"WAITING_FOR_FILE", "FILE_STABLE", "PROCESSING", "ORACLE_KO"}
        if state == "STOPPED" and process_alive:
            state = "WAITING_FOR_FILE"
        elif state == "STOPPED":
            process_alive = False
        watcher_active = bool(process_alive or state in active_states)
        response_state = state if watcher_active else "STOPPED"
        response_label = "Surveillance active" if watcher_active else "Surveillance arrêtée"
        response_message = file_status.get("message") if watcher_active else "Surveillance locale arrêtée."
        if watcher_active and "arrêt" in str(response_message or "").lower():
            response_message = "En attente de fichier."
        response = {
            "success": True,
            "active": watcher_active,
            "watching": watcher_active,
            "oracle_ok": file_status.get("oracle_ok"),
            "ftp_ok": file_status.get("ftp_ok"),
            "oracle_label": "Oracle connecté" if file_status.get("oracle_ok") is True else "Oracle indisponible",
            "ftp_label": "FTP connecté" if file_status.get("ftp_ok") is True else "FTP indisponible",
            "state": response_state,
            "label": response_label,
            "state_label": response_label if watcher_active else "Surveillance arrêtée",
            "last_detected_file": file_status.get("last_detected_file"),
            "message": response_message or ("En attente de fichier." if watcher_active else "Surveillance locale arrêtée."),
            "watch_dir": file_status.get("watch_dir"),
            "timestamp": file_status.get("timestamp"),
        }

        process_data = _read_json_file(ELT_WATCH_PROCESS_FILE, {})
        if isinstance(process_data, dict) and process_data.get("pid"):
            response["pid"] = process_data.get("pid")

        _log_response("[ELT WATCH] response", response)
        return response
    except Exception as exc:
        response = {
            "success": False,
            "active": False,
            "watching": False,
            "state": "STOPPED",
            "state_label": "Surveillance arrêtée",
            "message": f"Erreur lors de la verification du statut : {str(exc)}",
        }
        _log_response("[ELT WATCH] response", response)
        return response


def resolve_elt_path(path: str) -> Path:
    """
    Convert a relative path returned by ELT into an absolute path inside ELT_PROJECT_DIR.
    """
    if not path:
        raise ValueError("Chemin de fichier manquant.")

    normalized_path = str(path).replace("\\", os.sep)
    file_path = Path(normalized_path)

    if not file_path.is_absolute():
        file_path = ELT_PROJECT_DIR / file_path

    resolved_path = file_path.resolve()
    project_dir = ELT_PROJECT_DIR.resolve()

    if project_dir not in resolved_path.parents and resolved_path != project_dir:
        raise ValueError("Chemin de fichier ELT non autorise.")

    return resolved_path


def read_csv_rows(path: str) -> dict[str, Any]:
    csv_path = resolve_elt_path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV introuvable : {csv_path}")

    rows = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({column: row.get(column, "") for column in TECHNICAL_TASK_COLUMNS})

    return {
        "columns": TECHNICAL_TASK_COLUMNS,
        "rows": rows,
        "absolute_path": str(csv_path),
    }


def read_txt_report(path: str) -> dict[str, Any]:
    txt_path = resolve_elt_path(path)
    if not txt_path.exists():
        raise FileNotFoundError(f"TXT introuvable : {txt_path}")

    latest = get_latest_report() or {}
    latest_txt = latest.get("txt_report_path") or latest.get("txt_path")
    if latest_txt:
        try:
            if resolve_elt_path(latest_txt) == txt_path:
                return {
                    "content": _build_clean_txt_report(latest),
                    "absolute_path": str(txt_path),
                }
        except Exception:
            pass

    with open(txt_path, "r", encoding="utf-8") as f:
        return {
            "content": f.read(),
            "absolute_path": str(txt_path),
        }


def _pdf_escape(text: Any) -> str:
    value = str(text if text is not None else "")
    return (
        value.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("\r", "")
    )


def _wrap_text(text: str, max_chars: int = 92) -> list[str]:
    words = str(text or "").replace("\t", " ").split()
    if not words:
        return [""]

    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > max_chars and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def build_pdf_report(path: str | None = None) -> tuple[bytes, str]:
    _log("[PDF] build_pdf_report started")
    report = get_latest_report() or {}
    filename = "elt-report.pdf"

    if path:
        txt = read_txt_report(path)
        filename = f"{Path(txt['absolute_path']).stem}.pdf"
    elif report.get("txt_report_path") or report.get("txt_path"):
        txt = read_txt_report(report.get("txt_report_path") or report.get("txt_path"))
        filename = f"{Path(txt['absolute_path']).stem}.pdf"
    else:
        txt = {"content": ""}

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    employee = report.get("employee_report") or {}
    flows = employee.get("flows") or {}
    tech = employee.get("technical_summary") or {}
    diagnostic = employee.get("diagnostic") or {}
    status = report.get("status") or employee.get("global_status")
    scenario = report.get("scenario_label") or _scenario_label(report.get("scenario") or employee.get("scenario"))

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.25 * cm,
        leftMargin=1.25 * cm,
        topMargin=1.1 * cm,
        bottomMargin=1.1 * cm,
        title=REPORT_DISPLAY_NAME,
    )

    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "TTTitle",
            parent=base["Title"],
            alignment=TA_LEFT,
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#071d5b"),
            spaceAfter=2,
        ),
        "subtitle": ParagraphStyle(
            "TTSubtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#475467"),
        ),
        "section": ParagraphStyle(
            "TTSection",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#071d5b"),
            spaceBefore=8,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "TTBody",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#344054"),
        ),
        "center": ParagraphStyle(
            "TTCenter",
            parent=base["Normal"],
            alignment=TA_CENTER,
            fontName="Helvetica-Bold",
            fontSize=9,
            textColor=colors.white,
        ),
    }

    def p(text: Any, style: str = "body") -> Paragraph:
        safe = str(text if text not in (None, "") else "-").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return Paragraph(safe, styles[style])

    def status_color(value: Any):
        normalized = str(value or "").upper()
        if normalized in {"COMPLETED", "SUCCESS", "SUCCÈS"}:
            return colors.HexColor("#027a48")
        if normalized in {"FAILED", "FAILED_INSERT", "FAILED_CONTROL", "ÉCHEC"}:
            return colors.HexColor("#b42318")
        if normalized in {"PARTIAL_FAILURE", "RUNNING", "INITIALIZING"}:
            return colors.HexColor("#b54708")
        return colors.HexColor("#475467")

    def small_table(rows, widths=None):
        table = Table(rows, colWidths=widths, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef4ff")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#071d5b")),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d0d5dd")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        return table

    def flow_rows(key: str):
        flow = flows.get(key) or {}
        period = f"{flow.get('min_file_date') or '-'} au {flow.get('max_file_date') or '-'}"
        return [
            [p("Indicateur"), p("Valeur")],
            [p("Statut du flux"), p(flow.get("status"))],
            [p("Nombre de fichiers"), p(flow.get("file_count", 0))],
            [p("Période des fichiers"), p(period)],
            [p("Dernier traitement"), p(flow.get("last_processing_date"))],
            [p("Lignes fichier"), p(flow.get("total_file_rows", 0))],
            [p("Lignes insérées"), p(flow.get("total_inserted_rows", 0))],
            [p("Lignes rejetées"), p(flow.get("total_error_rows", 0))],
        ]

    story = []
    header_cells = []
    if TT_LOGO_FILE.exists():
        header_cells.append(Image(str(TT_LOGO_FILE), width=3.1 * cm, height=1.55 * cm, kind="proportional"))
    else:
        header_cells.append(p("Tunisie Telecom", "title"))
    header_cells.append([
        p(REPORT_DISPLAY_NAME, "title"),
        p("Supervision des flux Avance et Remboursement", "subtitle"),
    ])
    header = Table([header_cells], colWidths=[3.5 * cm, 14.0 * cm])
    header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fbff")),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#b2ddff")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.extend([header, Spacer(1, 0.22 * cm)])

    status_badge = Table([[p(_status_label(status), "center")]], colWidths=[5.2 * cm])
    status_badge.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), status_color(status)),
        ("BOX", (0, 0), (-1, -1), 0, status_color(status)),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))

    story.append(p("Informations générales", "section"))
    story.append(small_table([
        [p("Date de génération"), p(employee.get("generated_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")), p("Statut global"), status_badge],
        [p("Scénario utilisé"), p(scenario), p("Run ID"), p(report.get("run_id"))],
        [p("Oracle"), p("Connecté" if report.get("oracle_ok") is True or employee.get("oracle_ok") is True else "Indisponible"), p("FTP"), p("Connecté" if report.get("ftp_ok") is True or employee.get("ftp_ok") is True else "Indisponible")],
    ], [4.2 * cm, 5.0 * cm, 3.2 * cm, 5.1 * cm]))

    conclusion = employee.get("final_conclusion") or employee.get("employee_summary") or "Traitement terminé."

    if diagnostic.get("available") or str(status or "").upper() in {"FAILED", "PARTIAL_FAILURE"}:
        story.append(p("Diagnostic", "section"))
        story.append(small_table([
            [p("Cause"), p(diagnostic.get("cause") or diagnostic.get("reason") or employee.get("failure_cause") or "Non renseigné")],
            [p("Action recommandée"), p(diagnostic.get("recommended_action") or diagnostic.get("final_action") or "Non renseigné")],
        ], [4.2 * cm, 13.3 * cm]))

    story.append(p("Flux Avance", "section"))
    story.append(small_table(flow_rows("adv"), [5.6 * cm, 11.9 * cm]))
    story.append(p("Flux Remboursement", "section"))
    story.append(small_table(flow_rows("rev"), [5.6 * cm, 11.9 * cm]))

    story.append(p("Conclusion métier", "section"))
    story.append(p(conclusion))

    def footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#d0d5dd"))
        canvas.line(1.25 * cm, 1.0 * cm, 19.7 * cm, 1.0 * cm)
        canvas.setFillColor(colors.HexColor("#475467"))
        canvas.setFont("Helvetica", 8)
        canvas.drawString(1.25 * cm, 0.62 * cm, "Tunisie Telecom")
        canvas.drawCentredString(10.5 * cm, 0.62 * cm, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        canvas.drawRightString(19.7 * cm, 0.62 * cm, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    _log("[PDF] build_pdf_report success")
    return buffer.getvalue(), filename


def _save_latest_report(result: dict[str, Any]) -> None:
    ELT_LATEST_REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(ELT_LATEST_REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=4, ensure_ascii=False)
