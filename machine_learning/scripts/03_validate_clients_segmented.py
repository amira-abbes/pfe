import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]

EXPORTS_DIR = BASE_DIR / "data" / "exports"
REPORTS_DIR = BASE_DIR / "reports"

CLIENTS_FILE = EXPORTS_DIR / "clients_segmented.csv"
REPORT_FILE = REPORTS_DIR / "clients_segmented_validation_report.txt"


REQUIRED_COLUMNS = [
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


def log(lines, message=""):
    print(message)
    lines.append(str(message))


def main():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    lines = []

    log(lines, "=" * 90)
    log(lines, "Validation du fichier clients_segmented.csv")
    log(lines, "=" * 90)

    if not CLIENTS_FILE.exists():
        raise FileNotFoundError(f"Fichier introuvable : {CLIENTS_FILE}")

    df = pd.read_csv(CLIENTS_FILE)

    log(lines, "\n1. Dimensions")
    log(lines, f"Lignes  : {df.shape[0]}")
    log(lines, f"Colonnes: {df.shape[1]}")

    log(lines, "\n2. Colonnes obligatoires")
    missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]

    if missing_cols:
        log(lines, "Colonnes manquantes :")
        for col in missing_cols:
            log(lines, f" - {col}")
    else:
        log(lines, "Toutes les colonnes obligatoires sont présentes.")

    log(lines, "\n3. Doublons et identifiants")
    duplicated_msisdn = df["msisdn"].duplicated().sum()
    empty_msisdn = df["msisdn"].isna().sum()

    log(lines, f"Doublons msisdn : {duplicated_msisdn}")
    log(lines, f"msisdn vides    : {empty_msisdn}")

    log(lines, "\n4. Valeurs risk_tier")
    risk_tiers = df["risk_tier"].value_counts(dropna=False)
    log(lines, str(risk_tiers))

    allowed_tiers = {"low", "medium", "high"}
    invalid_tiers = sorted(set(df["risk_tier"].dropna().astype(str)) - allowed_tiers)

    if invalid_tiers:
        log(lines, f"risk_tier invalides : {invalid_tiers}")
    else:
        log(lines, "Tous les risk_tier sont valides : low / medium / high.")

    log(lines, "\n5. Scores de risque")
    score = pd.to_numeric(df["final_risk_score"], errors="coerce")

    log(lines, f"Score min  : {score.min()}")
    log(lines, f"Score max  : {score.max()}")
    log(lines, f"Score mean : {score.mean()}")

    below_zero = (score < 0).sum()
    above_one = (score > 1).sum()
    missing_score = score.isna().sum()

    log(lines, f"Scores < 0        : {below_zero}")
    log(lines, f"Scores > 1        : {above_one}")
    log(lines, f"Scores manquants  : {missing_score}")

    log(lines, "\n6. Cohérence score / risk_tier")
    coherence_table = df.groupby("risk_tier")["final_risk_score"].agg(
        count="count",
        min="min",
        mean="mean",
        max="max"
    ).sort_index()

    log(lines, str(coherence_table))

    log(lines, "\n7. Clusters")
    clusters = df["cluster_name"].value_counts(dropna=False)
    log(lines, str(clusters))

    log(lines, "\n8. Anomalies")
    anomalies = df["is_anomaly"].value_counts(dropna=False)
    log(lines, str(anomalies))

    log(lines, "\n9. top_drivers")
    missing_drivers = df["top_drivers"].isna().sum()
    empty_drivers = (df["top_drivers"].astype(str).str.strip() == "").sum()

    log(lines, f"top_drivers manquants : {missing_drivers}")
    log(lines, f"top_drivers vides     : {empty_drivers}")

    log(lines, "\n10. Aperçu")
    preview_cols = [
        "msisdn",
        "cluster_name",
        "risk_tier",
        "final_risk_score",
        "is_anomaly",
        "top_drivers",
    ]
    log(lines, str(df[preview_cols].head(10)))

    log(lines, "\n11. Conclusion")

    errors = []

    if df.shape[0] != 9748:
        errors.append("Nombre de lignes différent de 9748.")

    if df.shape[1] != 25:
        errors.append("Nombre de colonnes différent de 25.")

    if missing_cols:
        errors.append("Colonnes obligatoires manquantes.")

    if duplicated_msisdn > 0:
        errors.append("Doublons msisdn détectés.")

    if empty_msisdn > 0:
        errors.append("msisdn vides détectés.")

    if invalid_tiers:
        errors.append("risk_tier invalides détectés.")

    if below_zero > 0 or above_one > 0 or missing_score > 0:
        errors.append("Scores de risque hors intervalle ou manquants.")

    if missing_drivers > 0 or empty_drivers > 0:
        errors.append("top_drivers manquants ou vides.")

    if errors:
        log(lines, "VALIDATION : ATTENTION, corrections nécessaires.")
        for err in errors:
            log(lines, f" - {err}")
    else:
        log(lines, "VALIDATION : fichier clients_segmented.csv conforme pour intégration agentic/backend.")

    REPORT_FILE.write_text("\n".join(lines), encoding="utf-8")

    log(lines, "\n" + "=" * 90)
    log(lines, f"Rapport sauvegardé : {REPORT_FILE}")
    log(lines, "=" * 90)


if __name__ == "__main__":
    main()