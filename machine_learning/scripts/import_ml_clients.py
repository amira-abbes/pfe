import json
import pandas as pd
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import JSONB, BOOLEAN, INTEGER, DOUBLE_PRECISION, VARCHAR


# ==========================================================
# CONFIGURATION
# ==========================================================

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent

CSV_PATH = PROJECT_DIR / "machine_learning" / "data" / "exports" / "clients_segmented.csv"

DATABASE_URL = "postgresql+psycopg://postgres:123@127.0.0.1:5433/tt_internal_platform"


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


# ==========================================================
# OUTILS DE NETTOYAGE
# ==========================================================

def clean_boolean_column(series: pd.Series) -> pd.Series:
    """
    Convertit une colonne en booléen sans erreur.
    Important : astype(bool) est dangereux car la string 'False' peut devenir True.
    """
    return (
        series
        .astype(str)
        .str.strip()
        .str.lower()
        .map({
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
        })
        .fillna(False)
        .astype(bool)
    )


def parse_json_col(val):
    if not val or pd.isna(val):
        return []
    if isinstance(val, (list, dict)):
        return val
    try:
        return json.loads(val)
    except Exception:
        return []


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Nettoie et prépare le DataFrame avant insertion PostgreSQL.
    """

    missing_cols = [col for col in COLUMN_MAPPING.keys() if col not in df.columns]

    if missing_cols:
        raise ValueError(f"Colonnes manquantes dans le CSV : {missing_cols}")

    df = df[list(COLUMN_MAPPING.keys())].rename(columns=COLUMN_MAPPING)

    # MSISDN
    df["msisdn"] = df["msisdn"].astype(str).str.strip()

    # Supprimer les lignes sans MSISDN valide
    df = df[df["msisdn"].notna()]
    df = df[df["msisdn"].str.lower() != "nan"]
    df = df[df["msisdn"].str.strip() != ""]

    # Booléen
    bool_cols = [
        "is_anomaly",
        "has_debt",
        "uses_sos",
        "never_repaid",
        "full_repayer",
        "is_dormant_like",
    ]
    for col in bool_cols:
        df[col] = clean_boolean_column(df[col])

    # Entiers
    integer_cols = [
        "cluster_id",
        "risk_level",
        "nb_sos",
    ]

    for col in integer_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    # Numériques
    numeric_cols = [
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
    ]

    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Texte
    text_cols = [
        "state",
        "cluster_name",
        "risk_label",
        "risk_tier",
    ]

    for col in text_cols:
        df[col] = df[col].fillna("").astype(str).str.strip()

    # JSONB
    df["top_drivers"] = df["top_drivers"].apply(parse_json_col)

    df["imported_at"] = pd.Timestamp.now()

    return df


# ==========================================================
# CREATION DES TABLES
# ==========================================================

def create_schema_and_tables(conn):
    """
    Crée le schema ml et les tables nécessaires.
    """

    conn.execute(text("CREATE SCHEMA IF NOT EXISTS ml;"))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS ml.bad_debts_clients (
            msisdn VARCHAR(30) PRIMARY KEY,
            state VARCHAR(100),
            cluster_id INTEGER,
            cluster_name VARCHAR(100),
            risk_level INTEGER,
            risk_label VARCHAR(100),
            risk_tier VARCHAR(20),
            final_risk_score DOUBLE PRECISION,
            risk_score_raw DOUBLE PRECISION,
            is_anomaly BOOLEAN,
            anomaly_score DOUBLE PRECISION,
            top_drivers TEXT,

            avg_credit_amount DOUBLE PRECISION,
            avg_reimburse_ratio DOUBLE PRECISION,
            avg_days_since_credit DOUBLE PRECISION,
            total_outstanding_amount DOUBLE PRECISION,
            nb_sos INTEGER,
            debt_to_credit DOUBLE PRECISION,
            credit_intensity DOUBLE PRECISION,
            tenure_days DOUBLE PRECISION,

            has_debt INTEGER,
            uses_sos INTEGER,
            never_repaid INTEGER,
            full_repayer INTEGER,
            is_dormant_like INTEGER,

            imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS ml.ml_import_runs (
            id SERIAL PRIMARY KEY,
            file_name TEXT NOT NULL,
            rows_imported INTEGER DEFAULT 0,
            status VARCHAR(30) NOT NULL,
            error_message TEXT,
            imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            finished_at TIMESTAMP
        );
    """))


def table_has_column(conn, table_name: str, column_name: str) -> bool:
    return conn.execute(
        text("""
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'ml'
              AND table_name = :table_name
              AND column_name = :column_name
        """),
        {"table_name": table_name, "column_name": column_name},
    ).first() is not None


def existing_agent_tables(conn):
    rows = conn.execute(
        text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'ml'
              AND table_name IN ('agent_runs', 'agent_actions')
        """)
    ).scalars().all()
    order = ["agent_actions", "agent_runs"]
    return [name for name in order if name in set(rows)]


def log_import_success(conn, file_name: str, rows_imported: int):
    has_finished_at = table_has_column(conn, "ml_import_runs", "finished_at")
    if has_finished_at:
        conn.execute(
            text("""
                INSERT INTO ml.ml_import_runs
                (file_name, rows_imported, status, error_message, finished_at)
                VALUES (:file_name, :rows_imported, 'success', NULL, CURRENT_TIMESTAMP);
            """),
            {"file_name": file_name, "rows_imported": rows_imported},
        )
    else:
        conn.execute(
            text("""
                INSERT INTO ml.ml_import_runs
                (file_name, rows_imported, status, error_message)
                VALUES (:file_name, :rows_imported, 'success', NULL);
            """),
            {"file_name": file_name, "rows_imported": rows_imported},
        )


def log_import_error(conn, file_name: str, error_message: str):
    has_finished_at = table_has_column(conn, "ml_import_runs", "finished_at")
    if has_finished_at:
        conn.execute(
            text("""
                INSERT INTO ml.ml_import_runs
                (file_name, rows_imported, status, error_message, finished_at)
                VALUES (:file_name, 0, 'failed', :error_message, CURRENT_TIMESTAMP);
            """),
            {"file_name": file_name, "error_message": error_message[:1000]},
        )
    else:
        conn.execute(
            text("""
                INSERT INTO ml.ml_import_runs
                (file_name, rows_imported, status, error_message)
                VALUES (:file_name, 0, 'failed', :error_message);
            """),
            {"file_name": file_name, "error_message": error_message[:1000]},
        )


# ==========================================================
# IMPORT PRINCIPAL
# ==========================================================

def import_clients_segmented():
    print("=" * 90)
    print("IMPORT ML : clients_segmented.csv vers PostgreSQL")
    print("Table cible : ml.bad_debts_clients")
    print("=" * 90)

    if not CSV_PATH.exists():
        raise FileNotFoundError(f"Fichier introuvable : {CSV_PATH}")

    print(f"Fichier trouvé : {CSV_PATH}")

    print("Lecture du CSV...")
    df = pd.read_csv(CSV_PATH)

    print(f"CSV chargé : {df.shape[0]} lignes x {df.shape[1]} colonnes")

    print("Nettoyage des données...")
    df = clean_dataframe(df)

    print(f"Données prêtes pour import : {df.shape[0]} lignes")

    if df.empty:
        raise ValueError("Le DataFrame est vide après nettoyage. Import annulé.")

    print("Connexion PostgreSQL...")
    engine = create_engine(DATABASE_URL)

    try:
        with engine.begin() as conn:
            print("Création du schema et des tables...")
            create_schema_and_tables(conn)

            print("Vidage de la table ml.bad_debts_clients...")
            conn.execute(text("TRUNCATE TABLE ml.bad_debts_clients;"))

            agent_tables = existing_agent_tables(conn)
            if agent_tables:
                print("Nettoyage des analyses client du cycle précédent...")
                conn.execute(text(f"TRUNCATE TABLE {', '.join(f'ml.{name}' for name in agent_tables)} RESTART IDENTITY;"))

            print("Insertion des données dans PostgreSQL...")
            df.to_sql(
                name="bad_debts_clients",
                con=conn,
                schema="ml",
                if_exists="append",
                index=False,
                method="multi",
                chunksize=1000,
                dtype={
                    "top_drivers": JSONB,
                    "has_debt": BOOLEAN,
                    "uses_sos": BOOLEAN,
                    "never_repaid": BOOLEAN,
                    "full_repayer": BOOLEAN,
                    "is_dormant_like": BOOLEAN,
                }
            )

            count = conn.execute(
                text("SELECT COUNT(*) FROM ml.bad_debts_clients;")
            ).scalar()

            log_import_success(
                conn=conn,
                file_name=CSV_PATH.name,
                rows_imported=count,
            )

        print("=" * 90)
        print(f"IMPORT TERMINÉ AVEC SUCCÈS : {count} lignes insérées")
        print("=" * 90)

    except Exception as e:
        print("=" * 90)
        print("ERREUR PENDANT L'IMPORT")
        print(str(e))
        print("=" * 90)

        try:
            with engine.begin() as conn:
                create_schema_and_tables(conn)
                log_import_error(
                    conn=conn,
                    file_name=CSV_PATH.name,
                    error_message=str(e),
                )
        except Exception as log_error:
            print("Impossible d'écrire le log d'erreur dans ml.ml_import_runs")
            print(str(log_error))

        raise


# ==========================================================
# MAIN
# ==========================================================

if __name__ == "__main__":
    import_clients_segmented()
