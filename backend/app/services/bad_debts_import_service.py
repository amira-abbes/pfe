import ast
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import UploadFile
from sqlalchemy import MetaData, Table, text
from sqlalchemy.orm import Session


PROJECT_DIR = Path(__file__).resolve().parents[3]
ML_DIR = PROJECT_DIR / "machine_learning"
RUNTIME_IMPORTS_DIR = PROJECT_DIR / "backend" / "runtime_data" / "ml_imports"
MERGE_SCRIPT = ML_DIR / "scripts" / "01_build_merged_dataset.py"
VALIDATE_SEGMENTED_SCRIPT = ML_DIR / "scripts" / "03_validate_clients_segmented.py"
ML_NOTEBOOK = ML_DIR / "notebooks" / "ml_clustering_baddebts.ipynb"
POPULATION_FILE = ML_DIR / "data" / "raw" / "Pop ML V PIPE (1).csv"
MERGED_DATASET = ML_DIR / "data" / "processed" / "merged_dataset_inner.csv"
SEGMENTED_EXPORT = ML_DIR / "data" / "exports" / "clients_segmented.csv"
EXECUTED_NOTEBOOK_NAME = "executed_ml_clustering_baddebts.ipynb"

POPULATION_IMPORT_ERROR = (
    "Ce fichier correspond à la base population historique. Veuillez importer le fichier SOS Solde "
    "au format XLSX ou un fichier clients_segmented.csv déjà préparé."
)

SEGMENTED_COLUMNS = [
    "msisdn",
    "STATE",
    "cluster_id",
    "cluster_name",
    "risk_level",
    "risk_label",
    "risk_tier",
    "final_risk_score",
    "risk_score_raw",
    "is_anomaly",
    "anomaly_score",
    "top_drivers",
    "AVG_CREDIT_AMOUNT",
    "AVG_REIMBURSE_RATIO",
    "AVG_DAYS_SINCE_CREDIT",
    "TOTAL_OUTSTANDING_AMOUNT",
    "NB_SOS",
    "debt_to_credit",
    "credit_intensity",
    "tenure_days",
    "has_debt",
    "uses_sos",
    "never_repaid",
    "full_repayer",
    "is_dormant_like",
]

COLUMN_MAPPING = {
    "msisdn": "msisdn",
    "STATE": "state",
    "cluster_id": "cluster_id",
    "cluster_name": "cluster_name",
    "risk_level": "risk_level",
    "risk_label": "risk_label",
    "risk_tier": "risk_tier",
    "final_risk_score": "final_risk_score",
    "risk_score_raw": "risk_score_raw",
    "is_anomaly": "is_anomaly",
    "anomaly_score": "anomaly_score",
    "top_drivers": "top_drivers",
    "AVG_CREDIT_AMOUNT": "avg_credit_amount",
    "AVG_REIMBURSE_RATIO": "avg_reimburse_ratio",
    "AVG_DAYS_SINCE_CREDIT": "avg_days_since_credit",
    "TOTAL_OUTSTANDING_AMOUNT": "total_outstanding_amount",
    "NB_SOS": "nb_sos",
    "debt_to_credit": "debt_to_credit",
    "credit_intensity": "credit_intensity",
    "tenure_days": "tenure_days",
    "has_debt": "has_debt",
    "uses_sos": "uses_sos",
    "never_repaid": "never_repaid",
    "full_repayer": "full_repayer",
    "is_dormant_like": "is_dormant_like",
}

APP_CLIENT_COLUMNS = [*COLUMN_MAPPING.values(), "imported_at"]
BOOLEAN_COLUMNS = [
    "is_anomaly",
    "has_debt",
    "uses_sos",
    "never_repaid",
    "full_repayer",
    "is_dormant_like",
]
INTEGER_COLUMNS = ["cluster_id", "risk_level", "nb_sos", "tenure_days"]
FLOAT_COLUMNS = [
    "final_risk_score",
    "risk_score_raw",
    "anomaly_score",
    "avg_credit_amount",
    "avg_reimburse_ratio",
    "avg_days_since_credit",
    "total_outstanding_amount",
    "debt_to_credit",
    "credit_intensity",
]
STRING_COLUMNS = ["state", "cluster_name", "risk_label", "risk_tier"]
logger = logging.getLogger(__name__)


class BadDebtsImportError(RuntimeError):
    pass


class BadDebtsImportService:
    def __init__(self, db: Session):
        self.db = db

    async def run_uploaded_import(self, file: UploadFile) -> dict[str, Any]:
        original_filename = file.filename or "fichier_importe"
        import_id = self.create_import_run(original_filename)
        try:
            raw_path = await self.save_uploaded_file(import_id, file)
            raw_df = self.validate_raw_file(raw_path)
            file_type = self._detect_file_type(original_filename, raw_path, raw_df)
            logger.info(
                "Bad Debts import received import_id=%s file=%s saved_path=%s detected_type=%s rows=%s columns=%s",
                import_id,
                original_filename,
                raw_path,
                file_type,
                raw_df.shape[0],
                list(raw_df.columns),
            )

            if file_type == "population":
                raise BadDebtsImportError(POPULATION_IMPORT_ERROR)
            if file_type == "segmented":
                segmented_path = self._copy_segmented_upload(import_id, raw_path)
                self._publish_segmented_for_scripts(segmented_path)
                pipeline_type = "segmented"
            elif file_type == "sos":
                merged_path = self.run_merge_pipeline(import_id, raw_path)
                segmented_path = self.run_ml_pipeline(import_id, merged_path)
                pipeline_type = "raw_sos"
            else:
                raise BadDebtsImportError(
                    "Type de fichier Bad Debts non reconnu. Importez un fichier SOS Solde valide "
                    "ou un fichier clients_segmented.csv déjà préparé."
                )
            self._run_segmented_validation_script(segmented_path)
            df = self.validate_segmented_output(segmented_path)
            rows_imported = self.replace_clients_transaction(import_id, df)
            return {
                "import_id": import_id,
                "status": "SUCCES",
                "rows_imported": rows_imported,
                "error_message": None,
                "pipeline_type": pipeline_type,
            }
        except Exception as exc:
            error_message = self._format_exception(exc)
            logger.exception("Bad Debts import failed for import_id=%s", import_id)
            self.mark_import_failed(import_id, error_message)
            return {"import_id": import_id, "status": "ECHEC", "rows_imported": 0, "error_message": error_message}

    def create_import_run(self, file_name: str) -> int:
        self._ensure_import_table()
        has_finished_at = self._column_exists("ml_import_runs", "finished_at")
        if has_finished_at:
            row = self.db.execute(
                text(
                    """
                    INSERT INTO ml.ml_import_runs (file_name, rows_imported, status, error_message, imported_at, finished_at)
                    VALUES (:file_name, 0, 'EN_COURS', NULL, NOW(), NULL)
                    RETURNING id
                    """
                ),
                {"file_name": file_name},
            ).scalar_one()
        else:
            row = self.db.execute(
                text(
                    """
                    INSERT INTO ml.ml_import_runs (file_name, rows_imported, status, error_message, imported_at)
                    VALUES (:file_name, 0, 'EN_COURS', NULL, NOW())
                    RETURNING id
                    """
                ),
                {"file_name": file_name},
            ).scalar_one()
        self.db.commit()
        return int(row)

    async def save_uploaded_file(self, import_id: int, file: UploadFile) -> Path:
        suffix = Path(file.filename or "").suffix.lower()
        target_dir = RUNTIME_IMPORTS_DIR / str(import_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"raw_file{suffix or '.csv'}"
        with target.open("wb") as buffer:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                buffer.write(chunk)
        return target

    def validate_raw_file(self, path: Path) -> pd.DataFrame:
        if path.suffix.lower() not in {".csv", ".xlsx", ".xls"}:
            raise BadDebtsImportError("Format non supporte. Utilisez un fichier CSV ou XLSX.")
        if not path.exists() or path.stat().st_size == 0:
            raise BadDebtsImportError("Le fichier importe est vide.")

        df = self._read_table(path)
        if df.empty:
            raise BadDebtsImportError("Le fichier ne contient aucune ligne exploitable.")
        if not self._find_column(df, {"MSISDN", "msisdn"}):
            raise BadDebtsImportError("Colonne client MSISDN introuvable.")
        return df

    def run_merge_pipeline(self, import_id: int, raw_path: Path) -> Path:
        import_dir = RUNTIME_IMPORTS_DIR / str(import_id)
        merged_path = import_dir / "merged_dataset_inner.csv"
        raw_df = self._read_table(raw_path)

        if self._has_segmented_contract(raw_df):
            raise BadDebtsImportError("Fichier segmenté détecté : la fusion ne doit pas être lancée.")

        if not self._find_column(raw_df, {"MSISDN", "msisdn"}):
            raise BadDebtsImportError("Fichier brut invalide : colonne MSISDN introuvable.")
        if not MERGE_SCRIPT.exists():
            raise BadDebtsImportError("Script de fusion ML introuvable.")
        if not POPULATION_FILE.exists() or POPULATION_FILE.stat().st_size == 0:
            raise BadDebtsImportError(f"Base population historique introuvable : {POPULATION_FILE}")

        logger.info(
            "Bad Debts import_id=%s launching merge script=%s pop_file=%s sos_file=%s output=%s",
            import_id,
            MERGE_SCRIPT,
            POPULATION_FILE,
            raw_path,
            merged_path,
        )
        self._run_command(
            [
                sys.executable,
                str(MERGE_SCRIPT),
            ],
            cwd=ML_DIR,
            label="fusion du fichier brut SOS",
            timeout_seconds=900,
            env={
                "BAD_DEBTS_SOS_FILE": str(raw_path),
                "BAD_DEBTS_OUTPUT_FILE": str(merged_path),
            },
        )
        if not merged_path.exists() or merged_path.stat().st_size == 0:
            raise BadDebtsImportError(
                "merged_dataset_inner.csv n'a pas ete genere apres la fusion SOS/population. "
                f"Script: {MERGE_SCRIPT}. SOS: {raw_path}. Population: {POPULATION_FILE}. "
                f"Output attendu: {merged_path}."
            )
        self._best_effort_copy(merged_path, MERGED_DATASET)
        return merged_path

    def run_ml_pipeline(self, import_id: int, merged_path: Path) -> Path:
        import_dir = RUNTIME_IMPORTS_DIR / str(import_id)
        segmented_path = import_dir / "clients_segmented.csv"
        executed_notebook_path = import_dir / EXECUTED_NOTEBOOK_NAME
        if not merged_path.exists() or merged_path.stat().st_size == 0:
            raise BadDebtsImportError("Dataset fusionné introuvable avant lancement ML.")
        if not ML_NOTEBOOK.exists():
            raise BadDebtsImportError("Notebook ML introuvable.")
        self._ensure_notebook_runtime_available()
        notebook_path = self._prepare_notebook_for_import(import_dir, merged_path)
        command = [
            sys.executable,
            "-m",
            "nbconvert",
            "--to",
            "notebook",
            "--execute",
            str(notebook_path),
            "--output",
            EXECUTED_NOTEBOOK_NAME,
            "--output-dir",
            str(import_dir),
            "--ExecutePreprocessor.timeout=2400",
            "--ExecutePreprocessor.kernel_name=python3",
        ]

        logger.info(
            "Bad Debts manual notebook test command: cd %s && %s",
            ML_DIR,
            " ".join(command),
        )
        logger.info(
            "Bad Debts notebook paths import_id=%s notebook=%s executed_notebook=%s merged_dataset=%s "
            "segmented_output=%s import_dir=%s processed_dir=%s exports_dir=%s",
            import_id,
            notebook_path,
            executed_notebook_path,
            merged_path,
            segmented_path,
            import_dir,
            MERGED_DATASET.parent,
            SEGMENTED_EXPORT.parent,
        )
        self._run_command(
            command,
            cwd=ML_DIR,
            label="segmentation ML",
            timeout_seconds=2400,
            env={
                "BAD_DEBTS_MERGED_FILE": str(merged_path),
                "BAD_DEBTS_EXPORT_DIR": str(import_dir),
                "BAD_DEBTS_CLIENTS_SEGMENTED_FILE": str(segmented_path),
            },
            failure_details=lambda result: self._notebook_failure_details(
                notebook_path=notebook_path,
                executed_notebook_path=executed_notebook_path,
                merged_path=merged_path,
                segmented_path=segmented_path,
                result=result,
            ),
        )
        if not segmented_path.exists() or segmented_path.stat().st_size == 0:
            raise BadDebtsImportError(
                "clients_segmented.csv n'a pas ete genere par le notebook ML. "
                f"Notebook execute: {executed_notebook_path}. Dataset utilise: {merged_path}. "
                f"Output attendu: {segmented_path}."
            )
        self._best_effort_copy(segmented_path, SEGMENTED_EXPORT)
        return segmented_path

    def _publish_segmented_for_scripts(self, segmented_path: Path) -> None:
        self._best_effort_copy(segmented_path, SEGMENTED_EXPORT)

    def _run_segmented_validation_script(self, segmented_path: Path) -> None:
        if not VALIDATE_SEGMENTED_SCRIPT.exists():
            raise BadDebtsImportError("Script de validation clients_segmented.csv introuvable.")
        self._publish_segmented_for_scripts(segmented_path)
        logger.info(
            "Bad Debts launching validation script=%s input=%s canonical_input=%s",
            VALIDATE_SEGMENTED_SCRIPT,
            segmented_path,
            SEGMENTED_EXPORT,
        )
        self._run_command(
            [sys.executable, str(VALIDATE_SEGMENTED_SCRIPT)],
            cwd=ML_DIR,
            label="validation du fichier clients_segmented.csv",
            timeout_seconds=300,
        )

    def _copy_segmented_upload(self, import_id: int, raw_path: Path) -> Path:
        target = RUNTIME_IMPORTS_DIR / str(import_id) / "clients_segmented.csv"
        if raw_path.suffix.lower() == ".csv":
            shutil.copy2(raw_path, target)
            return target
        df = self._read_table(raw_path)
        self._write_csv(df, target)
        return target

    def validate_segmented_output(self, segmented_path: Path) -> pd.DataFrame:
        if not segmented_path.exists() or segmented_path.stat().st_size == 0:
            raise BadDebtsImportError("clients_segmented.csv n'a pas ete genere.")

        df = self._standardize_segmented_columns(self._read_table(segmented_path))
        missing = [col for col in SEGMENTED_COLUMNS if col not in df.columns]
        if missing:
            provided = [str(col) for col in df.columns]
            raise BadDebtsImportError(
                "Colonnes manquantes dans clients_segmented.csv : "
                f"{missing}. Colonnes detectees : {provided}"
            )
        if df.empty:
            raise BadDebtsImportError("clients_segmented.csv ne contient aucun client.")

        df = self._clean_segmented_dataframe(df)
        invalid_tiers = sorted(set(df["risk_tier"].dropna().astype(str)) - {"low", "medium", "high"})
        if invalid_tiers:
            raise BadDebtsImportError(f"risk_tier invalides : {invalid_tiers}")
        if df["final_risk_score"].isna().any() or (df["final_risk_score"] < 0).any() or (df["final_risk_score"] > 1).any():
            raise BadDebtsImportError("final_risk_score doit etre compris entre 0 et 1.")
        return df

    def replace_clients_transaction(self, import_id: int, df: pd.DataFrame) -> int:
        prepared_df = self._prepare_dataframe_for_target_table(df)
        rows_imported = int(len(prepared_df))
        records = self._dataframe_to_records(prepared_df)
        try:
            target_table = Table(
                "bad_debts_clients",
                MetaData(schema="ml"),
                autoload_with=self.db.connection(),
            )
            self.db.execute(text("TRUNCATE TABLE ml.bad_debts_clients;"))
            if records:
                self.db.connection().execute(target_table.insert(), records)
            tables = self._existing_tables(["agent_actions", "agent_runs"])
            if tables:
                joined = ", ".join(f"ml.{name}" for name in tables)
                self.db.execute(text(f"TRUNCATE TABLE {joined} RESTART IDENTITY;"))
            self._mark_import_success(import_id, rows_imported)
            self.db.commit()
            return rows_imported
        except Exception:
            self.db.rollback()
            raise

    def mark_import_failed(self, import_id: int, error_message: str) -> None:
        self.db.rollback()
        has_finished_at = self._column_exists("ml_import_runs", "finished_at")
        params = {"id": import_id, "error_message": error_message}
        if has_finished_at:
            query = """
                UPDATE ml.ml_import_runs
                SET status = 'ECHEC', rows_imported = 0, error_message = :error_message, finished_at = NOW()
                WHERE id = :id
            """
        else:
            query = """
                UPDATE ml.ml_import_runs
                SET status = 'ECHEC', rows_imported = 0, error_message = :error_message
                WHERE id = :id
            """
        self.db.execute(text(query), params)
        self.db.commit()

    def list_import_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        limit = min(max(int(limit or 20), 1), 100)
        has_finished_at = self._column_exists("ml_import_runs", "finished_at")
        finished_sql = "finished_at" if has_finished_at else "NULL AS finished_at"
        rows = self.db.execute(
            text(
                f"""
                SELECT id, file_name, rows_imported, status, error_message, imported_at, {finished_sql}
                FROM ml.ml_import_runs
                ORDER BY imported_at DESC, id DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).mappings().all()
        return [dict(row) for row in rows]

    def get_latest_import_run(self) -> dict[str, Any] | None:
        rows = self.list_import_runs(limit=1)
        return rows[0] if rows else None

    def get_import_run(self, import_id: int) -> dict[str, Any] | None:
        has_finished_at = self._column_exists("ml_import_runs", "finished_at")
        finished_sql = "finished_at" if has_finished_at else "NULL AS finished_at"
        row = self.db.execute(
            text(
                f"""
                SELECT id, file_name, rows_imported, status, error_message, imported_at, {finished_sql}
                FROM ml.ml_import_runs
                WHERE id = :id
                """
            ),
            {"id": import_id},
        ).mappings().first()
        return dict(row) if row else None

    def _mark_import_success(self, import_id: int, rows_imported: int) -> None:
        has_finished_at = self._column_exists("ml_import_runs", "finished_at")
        if has_finished_at:
            query = """
                UPDATE ml.ml_import_runs
                SET status = 'SUCCES', rows_imported = :rows_imported, error_message = NULL, finished_at = NOW()
                WHERE id = :id
            """
        else:
            query = """
                UPDATE ml.ml_import_runs
                SET status = 'SUCCES', rows_imported = :rows_imported, error_message = NULL
                WHERE id = :id
            """
        self.db.execute(text(query), {"id": import_id, "rows_imported": rows_imported})

    def _clean_segmented_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df[SEGMENTED_COLUMNS].rename(columns=COLUMN_MAPPING).copy()
        df = self._normalize_risk_columns(df)
        df["msisdn"] = df["msisdn"].map(self._normalize_msisdn)
        df = df[(df["msisdn"] != "") & (df["msisdn"].str.lower() != "nan")]
        for col in BOOLEAN_COLUMNS:
            df[col] = self._to_bool(df[col])
        for col in INTEGER_COLUMNS:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
        for col in FLOAT_COLUMNS:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["final_risk_score"] = self._normalize_probability_score(df["final_risk_score"])
        for col in STRING_COLUMNS:
            df[col] = df[col].fillna("").astype(str).str.strip()
        df["top_drivers"] = df["top_drivers"].map(self._normalize_top_drivers)
        df["risk_tier"] = df["risk_tier"].str.lower()
        duplicate_count = int(df["msisdn"].duplicated(keep="last").sum())
        if duplicate_count:
            logger.warning("Bad Debts import deduplicated %s duplicate MSISDN values", duplicate_count)
            df = df.drop_duplicates(subset=["msisdn"], keep="last").copy()
        df["imported_at"] = datetime.utcnow()
        return df

    def _read_table(self, path: Path) -> pd.DataFrame:
        if path.suffix.lower() in {".xlsx", ".xls"}:
            return pd.read_excel(path)
        return self._read_csv_safely(path)

    def _read_csv_safely(self, path: Path) -> pd.DataFrame:
        last_error: Exception | None = None
        for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin1", "ISO-8859-1"):
            for sep in ("|", ";", ",", "\t"):
                try:
                    df = pd.read_csv(path, encoding=encoding, sep=sep, engine="python")
                    if len(df.columns) > 1:
                        return df
                except Exception as exc:
                    last_error = exc
        raise BadDebtsImportError(f"Impossible de lire le CSV : {last_error}")

    def _write_csv(self, df: pd.DataFrame, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False, encoding="utf-8-sig")

    def _ensure_notebook_runtime_available(self) -> None:
        result = subprocess.run(
            [sys.executable, "-c", "import jupyter, nbconvert, ipykernel"],
            cwd=str(ML_DIR),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return
        details = "\n".join(part for part in [(result.stdout or "").strip(), (result.stderr or "").strip()] if part)
        missing_match = re.search(r"No module named ['\"]([^'\"]+)['\"]", details)
        if missing_match and missing_match.group(1) in {"jupyter", "nbconvert", "ipykernel"}:
            raise BadDebtsImportError(
                "Le notebook ML ne peut pas être exécuté car Jupyter/nbconvert/ipykernel "
                f"n’est pas installé dans le venv backend. Package manquant: {missing_match.group(1)}. "
                f"Details: {details or 'aucune sortie'}"
            )
        missing = f" Package Python manquant: {missing_match.group(1)}." if missing_match else ""
        if "zmq" in details.lower():
            missing = " Package Python invalide ou mal installe: pyzmq/zmq."
        raise BadDebtsImportError(
            "Le notebook ML ne peut pas être exécuté car l'environnement notebook du venv backend "
            f"est invalide ou incomplet.{missing} Details: {details or 'aucune sortie'}"
        )

    def _prepare_notebook_for_import(self, import_dir: Path, merged_path: Path) -> Path:
        notebook = json.loads(ML_NOTEBOOK.read_text(encoding="utf-8"))
        merged_literal = f"Path(os.environ.get('BAD_DEBTS_MERGED_FILE', r{str(merged_path)!r}))"
        export_literal = f"Path(os.environ.get('BAD_DEBTS_EXPORT_DIR', r{str(import_dir)!r}))"
        clients_literal = f"Path(os.environ.get('BAD_DEBTS_CLIENTS_SEGMENTED_FILE', str(EXPORT_DIR / 'clients_segmented.csv')))"
        replacements = {
            "from pathlib import Path": "from pathlib import Path\nimport os",
            'DATA_PATH = ML_DIR / "data" / "processed" / "merged_dataset_inner.csv"': f"DATA_PATH = {merged_literal}",
            'EXPORT_DIR = ML_DIR / "data" / "exports"': f"EXPORT_DIR = {export_literal}",
            'OUT_DIR = ML_DIR / "data" / "exports"': f"OUT_DIR = {export_literal}",
            'OUT_PATH = OUT_DIR / "clients_segmented.csv"': f"OUT_PATH = {clients_literal}",
            'CLIENTS_FILE = EXPORT_DIR / "clients_segmented.csv"': f"CLIENTS_FILE = {clients_literal}",
        }
        for cell in notebook.get("cells", []):
            source = "".join(cell.get("source", []))
            for old, new in replacements.items():
                source = source.replace(old, new)
            cell["source"] = source.splitlines(keepends=True)
        notebook.setdefault("metadata", {})["kernelspec"] = {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        }
        target = import_dir / "ml_clustering_baddebts_import.ipynb"
        target.write_text(json.dumps(notebook, ensure_ascii=False), encoding="utf-8")
        return target

    def _best_effort_copy(self, source: Path, target: Path) -> None:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        except OSError:
            # The runtime artifact remains authoritative for the transaction.
            # A locked OneDrive/Excel file must not fail an otherwise valid import.
            return

    def _run_command(
        self,
        command: list[str],
        *,
        cwd: Path,
        label: str,
        timeout_seconds: int,
        env: dict[str, str] | None = None,
        failure_details: Any | None = None,
    ) -> None:
        command_env = os.environ.copy()
        if env:
            command_env.update(env)
        logger.info(
            "Bad Debts command start label=%s cwd=%s command=%s env_overrides=%s",
            label,
            cwd,
            command,
            env or {},
        )
        try:
            result = subprocess.run(
                command,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
                env=command_env,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = self._decode_subprocess_output(exc.stdout)
            stderr = self._decode_subprocess_output(exc.stderr)
            raise BadDebtsImportError(
                f"Timeout pendant {label} apres {timeout_seconds}s. Commande: {' '.join(command)}. "
                f"stdout: {stdout or 'vide'}. stderr: {stderr or 'vide'}"
            ) from exc
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        logger.info(
            "Bad Debts command finished label=%s returncode=%s stdout=%s stderr=%s",
            label,
            result.returncode,
            stdout,
            stderr,
        )
        if result.returncode != 0:
            details = stderr or stdout or "aucune sortie stdout/stderr"
            extra_details = ""
            if failure_details is not None:
                try:
                    extra_details = str(failure_details(result)).strip()
                except Exception as detail_exc:
                    extra_details = f"Impossible d'extraire les details de l'echec: {detail_exc}"
            raise BadDebtsImportError(
                f"Erreur pendant {label}. Commande: {' '.join(command)}. "
                f"returncode: {result.returncode}. stdout: {stdout or 'vide'}. stderr: {details}. "
                f"{extra_details}"
            )

    def _decode_subprocess_output(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode(errors="replace").strip()
        return str(value).strip()

    def _notebook_failure_details(
        self,
        *,
        notebook_path: Path,
        executed_notebook_path: Path,
        merged_path: Path,
        segmented_path: Path,
        result: subprocess.CompletedProcess[str],
    ) -> str:
        parts = [
            f"Notebook source: {notebook_path}",
            f"Notebook execute attendu: {executed_notebook_path}",
            f"Dataset merge injecte: {merged_path} (exists={merged_path.exists()}, size={merged_path.stat().st_size if merged_path.exists() else 0})",
            f"Output clients_segmented attendu: {segmented_path}",
            f"Commande test manuelle: cd {ML_DIR} && {sys.executable} -m nbconvert --to notebook --execute {notebook_path} --output {EXECUTED_NOTEBOOK_NAME} --output-dir {executed_notebook_path.parent} --ExecutePreprocessor.timeout=2400 --ExecutePreprocessor.kernel_name=python3",
        ]
        notebook_errors = self._extract_notebook_errors(executed_notebook_path)
        if notebook_errors:
            parts.append("Erreurs extraites du notebook execute:")
            parts.extend(notebook_errors)
        elif executed_notebook_path.exists():
            parts.append("Le notebook execute existe, mais aucune sortie de cellule en erreur n'a ete trouvee.")
        else:
            parts.append("Le notebook execute n'a pas ete genere par nbconvert.")

        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        missing_match = re.search(r"No module named ['\"]([^'\"]+)['\"]", f"{stderr}\n{stdout}")
        if missing_match:
            parts.append(f"Package Python manquant detecte: {missing_match.group(1)}")
        return "\n".join(parts)

    def _extract_notebook_errors(self, notebook_path: Path) -> list[str]:
        if not notebook_path.exists():
            return []
        try:
            notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return [f"Impossible de lire le notebook execute {notebook_path}: {exc}"]

        errors: list[str] = []
        for index, cell in enumerate(notebook.get("cells", []), start=1):
            for output in cell.get("outputs", []) or []:
                if output.get("output_type") != "error":
                    continue
                ename = output.get("ename") or "Erreur"
                evalue = output.get("evalue") or ""
                traceback_lines = output.get("traceback") or []
                traceback_text = "\n".join(str(line) for line in traceback_lines)
                errors.append(
                    f"Cellule {index}: ename={ename}; evalue={evalue}; traceback=\n{traceback_text}"
                )
        return errors

    def _detect_file_type(self, filename: str, path: Path, df: pd.DataFrame) -> str:
        normalized_name = self._normalize_filename(filename or path.name)
        if normalized_name == self._normalize_filename(POPULATION_FILE.name) or self._looks_like_population_file(df):
            return "population"
        if self._has_segmented_contract(df):
            return "segmented"
        if self._looks_like_sos_file(df):
            return "sos"
        return "unknown"

    def _looks_like_population_file(self, df: pd.DataFrame) -> bool:
        normalized_columns = {self._normalize_column_name(col) for col in df.columns}
        population_columns = {"msisdn", "state_in", "subscriber_type_in", "rate_plan", "account_activated_date"}
        return population_columns.issubset(normalized_columns) and normalized_columns.isdisjoint(self._sos_column_markers())

    def _looks_like_sos_file(self, df: pd.DataFrame) -> bool:
        normalized_columns = {self._normalize_column_name(col) for col in df.columns}
        return "msisdn" in normalized_columns and bool(normalized_columns & self._sos_column_markers())

    def _sos_column_markers(self) -> set[str]:
        return {
            "avg_credit_amount",
            "avg_credit_fee",
            "avg_reimbursed_amount",
            "avg_fee_reimbursed",
            "avg_reimburse_ratio",
            "avg_days_since_credit",
            "total_outstanding_amount",
            "total_outstanding_fee",
            "nb_sos",
        }

    def _normalize_filename(self, value: str) -> str:
        return re.sub(r"\s+", " ", Path(value).name.strip().lower())

    def _has_segmented_contract(self, df: pd.DataFrame) -> bool:
        normalized_df = self._standardize_segmented_columns(df)
        return all(col in normalized_df.columns for col in SEGMENTED_COLUMNS)

    def _find_column(self, df: pd.DataFrame, candidates: set[str]) -> str | None:
        lower = {str(col).lower(): str(col) for col in df.columns}
        for candidate in candidates:
            if candidate.lower() in lower:
                return lower[candidate.lower()]
        return None

    def _to_bool(self, series: pd.Series) -> pd.Series:
        return series.astype(str).str.strip().str.lower().map({
            "true": True,
            "1": True,
            "yes": True,
            "oui": True,
            "false": False,
            "0": False,
            "no": False,
            "non": False,
            "nan": False,
            "none": False,
            "": False,
        }).fillna(False).astype(bool)

    def _normalize_msisdn(self, value: Any) -> str:
        if pd.isna(value):
            return ""
        if isinstance(value, str):
            raw = value.strip()
        elif isinstance(value, (int, bool)):
            raw = str(int(value))
        elif isinstance(value, float):
            raw = str(int(value)) if value.is_integer() else format(value, "f")
        else:
            raw = str(value).strip()
        raw = raw.strip()
        if re.fullmatch(r"\d+\.0+", raw):
            raw = raw.split(".", 1)[0]
        return raw

    def _normalize_top_drivers(self, value: Any) -> Any:
        if isinstance(value, (list, dict)):
            return value
        if value in ("", None):
            return []
        if pd.isna(value):
            return []
        raw = str(value).strip()
        if not raw:
            return []
        for parser in (json.loads, ast.literal_eval):
            try:
                parsed = parser(raw)
                if isinstance(parsed, (list, dict, str, int, float, bool)) or parsed is None:
                    return parsed
            except Exception:
                continue
        return raw

    def _normalize_risk_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        normalized = df.copy()
        risk_level_values = {
            str(value).strip().lower()
            for value in normalized["risk_level"].dropna().tolist()
            if str(value).strip()
        }
        risk_tier_values = {
            str(value).strip().lower()
            for value in normalized["risk_tier"].dropna().tolist()
            if str(value).strip()
        }
        tier_labels = {"low", "medium", "high"}
        numeric_scale = {"1", "2", "3", "4", "5"}
        if risk_level_values and risk_level_values.issubset(tier_labels) and risk_tier_values.issubset(numeric_scale):
            logger.info("Bad Debts import detected swapped risk_level/risk_tier synthetic format; normalizing columns")
            normalized["risk_level"], normalized["risk_tier"] = normalized["risk_tier"], normalized["risk_level"]
        return normalized

    def _normalize_probability_score(self, series: pd.Series) -> pd.Series:
        numeric = pd.to_numeric(series, errors="coerce")
        max_value = numeric.max(skipna=True)
        if pd.notna(max_value) and max_value > 1 and max_value <= 100:
            logger.info("Bad Debts import detected percentage-based final_risk_score; converting to 0..1 scale")
            return numeric / 100.0
        return numeric

    def _standardize_segmented_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        rename_map: dict[str, str] = {}
        normalized_sources: dict[str, list[str]] = {}
        for column in df.columns:
            normalized = self._normalize_column_name(column)
            normalized_sources.setdefault(normalized, []).append(str(column))
        for expected in SEGMENTED_COLUMNS:
            if expected in df.columns:
                continue
            aliases = {
                self._normalize_column_name(expected),
                self._normalize_column_name(COLUMN_MAPPING[expected]),
            }
            matches = [source for alias in aliases for source in normalized_sources.get(alias, [])]
            if matches:
                rename_map[matches[0]] = expected
        return df.rename(columns=rename_map)

    def _normalize_column_name(self, value: Any) -> str:
        return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")

    def _prepare_dataframe_for_target_table(self, df: pd.DataFrame) -> pd.DataFrame:
        columns = self._get_table_columns("bad_debts_clients")
        db_columns = [column["column_name"] for column in columns]
        missing_in_table = [column for column in APP_CLIENT_COLUMNS if column not in db_columns]
        if missing_in_table:
            raise BadDebtsImportError(
                "La table ml.bad_debts_clients ne contient pas les colonnes attendues par l'application : "
                f"{missing_in_table}. Colonnes presentes en base : {db_columns}"
            )

        missing_required_in_df = [
            column["column_name"]
            for column in columns
            if column["column_name"] not in df.columns
            and column["is_nullable"] == "NO"
            and column["column_default"] is None
        ]
        if missing_required_in_df:
            raise BadDebtsImportError(
                "Le fichier ne fournit pas toutes les colonnes requises pour ml.bad_debts_clients : "
                f"{missing_required_in_df}. Colonnes fichier : {list(df.columns)}. Colonnes base : {db_columns}"
            )

        extra_df_columns = [column for column in df.columns if column not in db_columns]
        if extra_df_columns:
            logger.info("Bad Debts import ignored extra columns not present in database: %s", extra_df_columns)

        prepared = df.copy()
        for column in db_columns:
            if column not in prepared.columns:
                prepared[column] = None
        return prepared.loc[:, db_columns]

    def _get_table_columns(self, table_name: str) -> list[dict[str, Any]]:
        rows = self.db.execute(
            text(
                """
                SELECT column_name, data_type, udt_name, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = 'ml'
                  AND table_name = :table_name
                ORDER BY ordinal_position
                """
            ),
            {"table_name": table_name},
        ).mappings().all()
        if not rows:
            raise BadDebtsImportError(f"Table introuvable : ml.{table_name}")
        return [dict(row) for row in rows]

    def _dataframe_to_records(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for record in df.to_dict(orient="records"):
            normalized_record: dict[str, Any] = {}
            for key, value in record.items():
                normalized_record[key] = self._normalize_record_value(value)
            records.append(normalized_record)
        return records

    def _normalize_record_value(self, value: Any) -> Any:
        if isinstance(value, (list, dict)):
            return value
        if isinstance(value, pd.Timestamp):
            return value.to_pydatetime()
        if hasattr(value, "item"):
            try:
                value = value.item()
            except Exception:
                return value
        if pd.isna(value):
            return None
        return value

    def _format_exception(self, exc: Exception) -> str:
        message = str(exc).strip() or exc.__class__.__name__
        if isinstance(exc, BadDebtsImportError):
            return message
        origin = getattr(exc, "orig", None)
        details = [f"{exc.__class__.__name__}: {message}"]
        if origin is not None:
            details.append(f"Origine SQL: {origin!r}")
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip()
        if tb:
            details.append(tb)
        return "\n\n".join(details)

    def _ensure_import_table(self) -> None:
        self.db.execute(text("CREATE SCHEMA IF NOT EXISTS ml;"))
        self.db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS ml.ml_import_runs (
                    id SERIAL PRIMARY KEY,
                    file_name TEXT NOT NULL,
                    rows_imported INTEGER DEFAULT 0,
                    status VARCHAR(30) NOT NULL,
                    error_message TEXT,
                    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    finished_at TIMESTAMP
                )
                """
            )
        )
        self.db.commit()

    def _column_exists(self, table_name: str, column_name: str) -> bool:
        row = self.db.execute(
            text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'ml'
                  AND table_name = :table_name
                  AND column_name = :column_name
                """
            ),
            {"table_name": table_name, "column_name": column_name},
        ).first()
        return row is not None

    def _existing_tables(self, table_names: list[str]) -> list[str]:
        rows = self.db.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'ml'
                  AND table_name IN ('agent_actions', 'agent_runs')
                """
            )
        ).scalars().all()
        return [name for name in table_names if name in set(rows)]
