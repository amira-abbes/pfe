import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]

RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"

pop_file = RAW_DIR / "Pop ML V PIPE (1).csv"
sos_file = RAW_DIR / "SOS_SOLDE_DATA_ML_10K 1 (1).xlsx"
merged_file = PROCESSED_DIR / "merged_dataset_inner.csv"


def read_csv_safely(path: Path) -> pd.DataFrame:
    """
    Lecture robuste d'un fichier CSV entreprise.
    Teste plusieurs encodages et plusieurs séparateurs.
    Utile pour les fichiers exportés depuis Excel, Oracle, Windows, etc.
    """

    encodings = [
        "utf-8-sig",
        "utf-8",
        "cp1252",
        "latin1",
        "ISO-8859-1"
    ]

    separators = [
        "|",
        ";",
        ",",
        "\t"
    ]

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
    """
    Lecture sécurisée d'un fichier Excel.
    """

    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {path}")

    try:
        df = pd.read_excel(path)
        print(
            f"Lecture réussie : {path.name} | "
            f"lignes={df.shape[0]} | colonnes={df.shape[1]}"
        )
        return df

    except Exception as exc:
        raise RuntimeError(
            f"Impossible de lire le fichier Excel {path}. "
            f"Dernière erreur : {exc}"
        )


def print_dataset_info(name: str, df: pd.DataFrame):
    """
    Affiche les informations principales d'un dataset.
    """

    print("\n" + "=" * 80)
    print(f"DATASET : {name}")
    print("=" * 80)

    print(f"Lignes  : {df.shape[0]}")
    print(f"Colonnes: {df.shape[1]}")

    print("\nColonnes :")
    for col in df.columns:
        print(f" - {col}")

    print("\nAperçu des 5 premières lignes :")
    print(df.head())

    print("\nValeurs manquantes par colonne :")
    missing_values = df.isna().sum()
    missing_values = missing_values[missing_values > 0]

    if missing_values.empty:
        print("Aucune valeur manquante détectée.")
    else:
        print(missing_values)


def main():
    print("=" * 80)
    print("Vérification des fichiers Machine Learning Bad Debts")
    print("=" * 80)

    print("\nLecture base population client...")
    pop_df = read_csv_safely(pop_file)

    print("\nLecture base SOS Solde...")
    sos_df = read_excel_safely(sos_file)

    print("\nLecture base fusionnée ML...")
    merged_df = read_csv_safely(merged_file)

    print_dataset_info("Base population client", pop_df)
    print_dataset_info("Base SOS Solde", sos_df)
    print_dataset_info("Base fusionnée ML", merged_df)

    print("\n" + "=" * 80)
    print("Vérification terminée avec succès.")
    print("=" * 80)


if __name__ == "__main__":
    main()