import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import UploadFile
from sqlalchemy import text
from sqlalchemy.orm import Session


PROJECT_DIR = Path(__file__).resolve().parents[3]
ML_DIR = PROJECT_DIR / "machine_learning"
RUNTIME_IMPORTS_DIR = PROJECT_DIR / "backend" / "runtime_data" / "ml_imports"
MERGE_SCRIPT = ML_DIR / "scripts" / "01_build_merged_dataset.py"
ML_NOTEBOOK = ML_DIR / "notebooks" / "ml_clustering_baddebts.ipynb"
MERGED_DATASET = ML_DIR / "data" / "processed" / "merged_dataset_inner.csv"
SEGMENTED_EXPORT = ML_DIR / "data" / "exports" / "clients_segmented.csv"

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


class BadDebtsImportError(RuntimeError):
    pass


class BadDebtsImportService:
    def __init__(self, db: Session):
        self.db = db

    async def run_uploaded_import(self, file: UploadFile) -> dict[str, Any]:
        import_id = self.create_import_run(file.filename or "fichier_importe")
        try:
            raw_path = await self.save_uploaded_file(import_id, file)
            raw_df = self.validate_raw_file(raw_path)
            if self._has_segmented_contract(raw_df):
                segmented_path = self._copy_segmented_upload(import_id, raw_path)
                pipeline_type = "segmented"
            else:
                merged_path = self.run_merge_pipeline(import_id, raw_path)
                segmented_path = self.run_ml_pipeline(import_id, merged_path)
                pipeline_type = "raw_sos"
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
            self.mark_import_failed(import_id, str(exc))
            return {"import_id": import_id, "status": "ECHEC", "rows_imported": 0, "error_message": str(exc)}

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

        self._run_command(
            [
                sys.executable,
                str(MERGE_SCRIPT),
                "--sos-file",
                str(raw_path),
                "--output-file",
                str(merged_path),
            ],
            cwd=ML_DIR,
            label="fusion du fichier brut SOS",
            timeout_seconds=900,
        )
        if not merged_path.exists() or merged_path.stat().st_size == 0:
            raise BadDebtsImportError("merged_dataset_inner.csv n'a pas été généré.")
        self._best_effort_copy(merged_path, MERGED_DATASET)
        return merged_path

    def run_ml_pipeline(self, import_id: int, merged_path: Path) -> Path:
        import_dir = RUNTIME_IMPORTS_DIR / str(import_id)
        segmented_path = import_dir / "clients_segmented.csv"
        if not merged_path.exists() or merged_path.stat().st_size == 0:
            raise BadDebtsImportError("Dataset fusionné introuvable avant lancement ML.")
        if not ML_NOTEBOOK.exists():
            raise BadDebtsImportError("Notebook ML introuvable.")
        notebook_path = self._prepare_notebook_for_import(import_dir, merged_path)

        self._run_command(
            [
                sys.executable,
                "-m",
                "jupyter",
                "nbconvert",
                "--to",
                "notebook",
                "--execute",
                str(notebook_path),
                "--output",
                "executed_ml_clustering_baddebts.ipynb",
                "--output-dir",
                str(import_dir),
            ],
            cwd=ML_DIR,
            label="segmentation ML",
            timeout_seconds=2400,
        )
        if not segmented_path.exists() or segmented_path.stat().st_size == 0:
            raise BadDebtsImportError("clients_segmented.csv n'a pas été généré par le notebook ML.")
        self._best_effort_copy(segmented_path, SEGMENTED_EXPORT)
        return segmented_path

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

        df = self._read_table(segmented_path)
        missing = [col for col in SEGMENTED_COLUMNS if col not in df.columns]
        if missing:
            raise BadDebtsImportError(f"Colonnes manquantes dans clients_segmented.csv : {missing}")
        if df.empty:
            raise BadDebtsImportError("clients_segmented.csv ne contient aucun client.")

        df = self._clean_segmented_dataframe(df)
        if df["msisdn"].duplicated().any():
            raise BadDebtsImportError("Doublons MSISDN detectes dans clients_segmented.csv.")
        invalid_tiers = sorted(set(df["risk_tier"].dropna().astype(str)) - {"low", "medium", "high"})
        if invalid_tiers:
            raise BadDebtsImportError(f"risk_tier invalides : {invalid_tiers}")
        if df["final_risk_score"].isna().any() or (df["final_risk_score"] < 0).any() or (df["final_risk_score"] > 1).any():
            raise BadDebtsImportError("final_risk_score doit etre compris entre 0 et 1.")
        return df

    def replace_clients_transaction(self, import_id: int, df: pd.DataFrame) -> int:
        rows_imported = int(len(df))
        try:
            self.db.execute(text("TRUNCATE TABLE ml.bad_debts_clients;"))
            df.to_sql(
                name="bad_debts_clients",
                con=self.db.connection(),
                schema="ml",
                if_exists="append",
                index=False,
                method="multi",
                chunksize=1000,
            )
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
        params = {"id": import_id, "error_message": error_message[:1500]}
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
        df["msisdn"] = df["msisdn"].astype(str).str.strip().str.replace(".0", "", regex=False)
        df = df[(df["msisdn"] != "") & (df["msisdn"].str.lower() != "nan")]
        df["is_anomaly"] = self._to_bool(df["is_anomaly"])
        for col in ["cluster_id", "risk_level", "nb_sos", "has_debt", "uses_sos", "never_repaid", "full_repayer", "is_dormant_like"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
        for col in [
            "final_risk_score",
            "risk_score_raw",
            "anomaly_score",
            "avg_credit_amount",
            "avg_reimburse_ratio",
            "avg_days_since_credit",
            "total_outstanding_amount",
            "debt_to_credit",
            "credit_intensity",
            "tenure_days",
        ]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        for col in ["state", "cluster_name", "risk_label", "risk_tier", "top_drivers"]:
            df[col] = df[col].fillna("").astype(str).str.strip()
        df["risk_tier"] = df["risk_tier"].str.lower()
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

    def _prepare_notebook_for_import(self, import_dir: Path, merged_path: Path) -> Path:
        notebook = json.loads(ML_NOTEBOOK.read_text(encoding="utf-8"))
        merged_literal = f"Path(r{str(merged_path)!r})"
        export_literal = f"Path(r{str(import_dir)!r})"
        replacements = {
            'DATA_PATH = ML_DIR / "data" / "processed" / "merged_dataset_inner.csv"': f"DATA_PATH = {merged_literal}",
            'EXPORT_DIR = ML_DIR / "data" / "exports"': f"EXPORT_DIR = {export_literal}",
            'OUT_DIR = ML_DIR / "data" / "exports"': f"OUT_DIR = {export_literal}",
        }
        for cell in notebook.get("cells", []):
            source = "".join(cell.get("source", []))
            for old, new in replacements.items():
                source = source.replace(old, new)
            cell["source"] = source.splitlines(keepends=True)
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

    def _run_command(self, command: list[str], *, cwd: Path, label: str, timeout_seconds: int) -> None:
        result = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        if result.returncode != 0:
            stderr = (result.stderr or result.stdout or "").strip()
            raise BadDebtsImportError(f"Erreur pendant {label} : {stderr[:1500]}")

    def _has_segmented_contract(self, df: pd.DataFrame) -> bool:
        return all(col in df.columns for col in SEGMENTED_COLUMNS)

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
