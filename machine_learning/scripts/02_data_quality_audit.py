import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]

PROCESSED_DIR = BASE_DIR / "data" / "processed"
REPORTS_DIR = BASE_DIR / "reports"

DATASET_FILE = PROCESSED_DIR / "merged_dataset_inner.csv"
REPORT_FILE = REPORTS_DIR / "data_quality_report.txt"
MISSING_REPORT_FILE = REPORTS_DIR / "missing_values_report.csv"
NUMERIC_STATS_FILE = REPORTS_DIR / "numeric_statistics.csv"
CATEGORICAL_STATS_FILE = REPORTS_DIR / "categorical_statistics.csv"


def read_csv_safely(path: Path) -> pd.DataFrame:
    encodings = ["utf-8-sig", "utf-8", "cp1252", "latin1", "ISO-8859-1"]
    separators = [",", ";", "|", "\t"]

    last_error = None

    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {path}")

    for encoding in encodings:
        for sep in separators:
            try:
                df = pd.read_csv(path, encoding=encoding, sep=sep, engine="python")
                if df.shape[1] > 1:
                    print(
                        f"Lecture réussie : {path.name} | "
                        f"encoding={encoding} | sep='{sep}' | "
                        f"lignes={df.shape[0]} | colonnes={df.shape[1]}"
                    )
                    return df
            except Exception as exc:
                last_error = exc

    raise RuntimeError(
        f"Impossible de lire correctement le fichier {path}. "
        f"Dernière erreur : {last_error}"
    )


def log_line(lines: list[str], message: str = ""):
    print(message)
    lines.append(message)


def main():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    lines = []

    log_line(lines, "=" * 90)
    log_line(lines, "Audit qualité du dataset Machine Learning Bad Debts")
    log_line(lines, "=" * 90)

    df = read_csv_safely(DATASET_FILE)

    log_line(lines, "\n1. Dimensions du dataset")
    log_line(lines, f"Lignes  : {df.shape[0]}")
    log_line(lines, f"Colonnes: {df.shape[1]}")

    log_line(lines, "\n2. Colonnes disponibles")
    for col in df.columns:
        log_line(lines, f" - {col}")

    log_line(lines, "\n3. Types des colonnes")
    dtypes_text = df.dtypes.astype(str)
    for col, dtype in dtypes_text.items():
        log_line(lines, f" - {col}: {dtype}")

    log_line(lines, "\n4. Doublons")
    duplicated_rows = df.duplicated().sum()
    duplicated_msisdn = df["MSISDN"].duplicated().sum() if "MSISDN" in df.columns else "MSISDN absent"

    log_line(lines, f"Lignes totalement dupliquées : {duplicated_rows}")
    log_line(lines, f"Doublons MSISDN              : {duplicated_msisdn}")

    log_line(lines, "\n5. Valeurs manquantes")
    missing = df.isna().sum()
    missing_pct = (missing / len(df) * 100).round(2)

    missing_report = pd.DataFrame({
        "missing_count": missing,
        "missing_percent": missing_pct
    }).sort_values(by="missing_count", ascending=False)

    missing_report.to_csv(MISSING_REPORT_FILE, index=True, encoding="utf-8-sig")

    missing_nonzero = missing_report[missing_report["missing_count"] > 0]

    if missing_nonzero.empty:
        log_line(lines, "Aucune valeur manquante détectée.")
    else:
        log_line(lines, str(missing_nonzero))

    log_line(lines, "\n6. Statistiques numériques")
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()

    if numeric_cols:
        numeric_stats = df[numeric_cols].describe().T
        numeric_stats.to_csv(NUMERIC_STATS_FILE, encoding="utf-8-sig")
        log_line(lines, f"Colonnes numériques détectées : {len(numeric_cols)}")
        for col in numeric_cols:
            log_line(lines, f" - {col}")
    else:
        log_line(lines, "Aucune colonne numérique détectée.")

    log_line(lines, "\n7. Variables catégorielles")
    categorical_cols = df.select_dtypes(include=["object"]).columns.tolist()

    cat_rows = []

    for col in categorical_cols:
        unique_count = df[col].nunique(dropna=True)
        top_values = df[col].value_counts(dropna=False).head(10)

        log_line(lines, f"\nColonne catégorielle : {col}")
        log_line(lines, f"Nombre de valeurs distinctes : {unique_count}")
        log_line(lines, str(top_values))

        for value, count in top_values.items():
            cat_rows.append({
                "column": col,
                "value": value,
                "count": count
            })

    if cat_rows:
        pd.DataFrame(cat_rows).to_csv(CATEGORICAL_STATS_FILE, index=False, encoding="utf-8-sig")

    log_line(lines, "\n8. Contrôle des valeurs négatives sur variables financières")
    financial_cols = [
        "AVG_CREDIT_AMOUNT",
        "AVG_CREDIT_FEE",
        "AVG_REIMBURSED_AMOUNT",
        "AVG_FEE_REIMBURSED",
        "AVG_REIMBURSE_RATIO",
        "AVG_DAYS_SINCE_CREDIT",
        "TOTAL_OUTSTANDING_AMOUNT",
        "TOTAL_OUTSTANDING_FEE",
        "NB_SOS",
    ]

    for col in financial_cols:
        if col in df.columns:
            values = pd.to_numeric(df[col], errors="coerce")
            negative_count = (values < 0).sum()
            log_line(lines, f"{col}: valeurs négatives = {negative_count}")

    log_line(lines, "\n9. Contrôle des ratios")
    if "AVG_REIMBURSE_RATIO" in df.columns:
        ratio = pd.to_numeric(df["AVG_REIMBURSE_RATIO"], errors="coerce")
        below_zero = (ratio < 0).sum()
        above_one = (ratio > 1).sum()

        log_line(lines, f"AVG_REIMBURSE_RATIO < 0 : {below_zero}")
        log_line(lines, f"AVG_REIMBURSE_RATIO > 1 : {above_one}")

    log_line(lines, "\n10. Contrôle des dates d’activation")
    if "ACCOUNT_ACTIVATED_DATE" in df.columns:
        activation_dates = pd.to_datetime(df["ACCOUNT_ACTIVATED_DATE"], errors="coerce")
        invalid_dates = activation_dates.isna().sum()
        min_date = activation_dates.min()
        max_date = activation_dates.max()

        log_line(lines, f"Dates invalides ou manquantes : {invalid_dates}")
        log_line(lines, f"Date activation minimale      : {min_date}")
        log_line(lines, f"Date activation maximale      : {max_date}")

    log_line(lines, "\n11. Conclusion")
    log_line(lines, "Audit qualité terminé. Les rapports détaillés ont été générés dans machine_learning/reports.")

    REPORT_FILE.write_text("\n".join(lines), encoding="utf-8")

    log_line(lines, "\n" + "=" * 90)
    log_line(lines, f"Rapport texte sauvegardé : {REPORT_FILE}")
    log_line(lines, f"Rapport valeurs manquantes : {MISSING_REPORT_FILE}")
    log_line(lines, f"Statistiques numériques : {NUMERIC_STATS_FILE}")
    log_line(lines, f"Statistiques catégorielles : {CATEGORICAL_STATS_FILE}")
    log_line(lines, "=" * 90)


if __name__ == "__main__":
    main()