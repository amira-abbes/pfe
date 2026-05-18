import argparse
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]

RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"

POP_FILE = RAW_DIR / "Pop ML V PIPE (1).csv"
SOS_FILE = RAW_DIR / "SOS_SOLDE_DATA_ML_10K 1 (1).xlsx"

MERGED_FILE = PROCESSED_DIR / "merged_dataset_inner.csv"


def read_csv_safely(path: Path) -> pd.DataFrame:
    encodings = ["utf-8-sig", "utf-8", "cp1252", "latin1", "ISO-8859-1"]
    separators = ["|", ";", ",", "\t"]

    last_error = None

    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {path}")

    for encoding in encodings:
        for sep in separators:
            try:
                df = pd.read_csv(
                    path,
                    encoding=encoding,
                    sep=sep,
                    engine="python"
                )

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


def read_excel_safely(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {path}")

    df = pd.read_excel(path)
    print(
        f"Lecture réussie : {path.name} | "
        f"lignes={df.shape[0]} | colonnes={df.shape[1]}"
    )
    return df


def read_sos_file(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        return read_excel_safely(path)
    if suffix == ".csv":
        return read_csv_safely(path)
    raise ValueError(f"Format SOS non supporté : {path.suffix}")


def clean_msisdn(df: pd.DataFrame, dataset_name: str) -> pd.DataFrame:
    """
    Normalise la clé MSISDN pour garantir une jointure fiable.
    """
    if "MSISDN" not in df.columns:
        raise ValueError(f"La colonne MSISDN est absente dans {dataset_name}")

    df = df.copy()

    df["MSISDN"] = (
        df["MSISDN"]
        .astype(str)
        .str.strip()
        .str.replace(".0", "", regex=False)
    )

    df = df[df["MSISDN"].notna()]
    df = df[df["MSISDN"] != ""]
    df = df[df["MSISDN"].str.lower() != "nan"]

    print(f"{dataset_name} après nettoyage MSISDN : {df.shape[0]} lignes")

    return df


def main(sos_file: Path | None = None, output_file: Path | None = None):
    active_sos_file = sos_file or SOS_FILE
    active_merged_file = output_file or MERGED_FILE

    print("=" * 90)
    print("Construction du dataset fusionné Machine Learning Bad Debts")
    print("=" * 90)

    print("\n1. Lecture des sources brutes")
    pop_df = read_csv_safely(POP_FILE)
    sos_df = read_sos_file(active_sos_file)

    print("\n2. Dimensions initiales")
    print(f"Base population client : {pop_df.shape[0]} lignes x {pop_df.shape[1]} colonnes")
    print(f"Base SOS Solde         : {sos_df.shape[0]} lignes x {sos_df.shape[1]} colonnes")

    print("\n3. Nettoyage de la clé MSISDN")
    pop_df = clean_msisdn(pop_df, "Base population client")
    sos_df = clean_msisdn(sos_df, "Base SOS Solde")

    print("\n4. Vérification des doublons MSISDN")
    pop_duplicates = pop_df["MSISDN"].duplicated().sum()
    sos_duplicates = sos_df["MSISDN"].duplicated().sum()

    print(f"Doublons MSISDN population : {pop_duplicates}")
    print(f"Doublons MSISDN SOS Solde  : {sos_duplicates}")

    if pop_duplicates > 0:
        print("Suppression des doublons dans la base population client.")
        pop_df = pop_df.drop_duplicates(subset=["MSISDN"], keep="first")

    if sos_duplicates > 0:
        print("Suppression des doublons dans la base SOS Solde.")
        sos_df = sos_df.drop_duplicates(subset=["MSISDN"], keep="first")

    print("\n5. Jointure interne sur MSISDN")
    merged_df = pd.merge(
        pop_df,
        sos_df,
        on="MSISDN",
        how="inner"
    )

    print(f"Dataset fusionné final : {merged_df.shape[0]} lignes x {merged_df.shape[1]} colonnes")

    print("\n6. Valeurs manquantes dans le dataset fusionné")
    missing_values = merged_df.isna().sum()
    missing_values = missing_values[missing_values > 0]

    if missing_values.empty:
        print("Aucune valeur manquante détectée.")
    else:
        print(missing_values)

    print("\n7. Sauvegarde du dataset final")
    active_merged_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file = active_merged_file.with_name(f"{active_merged_file.stem}.tmp{active_merged_file.suffix}")
    merged_df.to_csv(temp_file, index=False, encoding="utf-8-sig")
    temp_file.replace(active_merged_file)

    print(f"Fichier sauvegardé : {active_merged_file}")

    print("\nColonnes du dataset final :")
    for col in merged_df.columns:
        print(f" - {col}")

    print("\n" + "=" * 90)
    print("Construction terminée avec succès.")
    print("=" * 90)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Construit merged_dataset_inner.csv pour le ML Bad Debts.")
    parser.add_argument("--sos-file", type=Path, default=None, help="Fichier SOS Solde uploadé à utiliser.")
    parser.add_argument("--output-file", type=Path, default=None, help="Chemin de sortie optionnel du dataset fusionné.")
    args = parser.parse_args()
    main(sos_file=args.sos_file, output_file=args.output_file)
