import pandas as pd
#pandas sert à manipuler des tableaux de données sous forme de DataFrame.
from pathlib import Path
#Path permet de gérer les chemins de fichiers proprement, sans écrire manuellement des chemins

BASE_DIR = Path(__file__).resolve().parents[1]
#Cette ligne définit le dossier principal du projet. : C:/projet/scripts/check_data.py


#prépare les chemins vers les dossiers où se trouvent les fichiers.
RAW_DIR = BASE_DIR / "data" / "raw" 

#Ce bloc définit les deux fichiers sources utilisés dans le Machine Learning.
pop_file = RAW_DIR / "Pop ML V PIPE (1).csv"
sos_file = RAW_DIR / "SOS_SOLDE_DATA_ML_10K 1 (1).xlsx"


def read_csv_safely(path: Path) -> pd.DataFrame:
    """
    Lecture robuste d'un fichier CSV entreprise.
    Teste plusieurs encodages et plusieurs séparateurs.
    Utile pour les fichiers exportés depuis Excel, Oracle, Windows, etc.
    Parce que les fichiers CSV peuvent avoir plusieurs formats :

encodage UTF-8 ;
encodage Windows cp1252 ;
séparateur ; ;
séparateur , ;
séparateur |, etc.
lire le CSV de manière robuste, en testant plusieurs formats possibles, et afficher une erreur claire si ça ne marche pas.
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
    #Cette variable va garder en mémoire la dernière erreur rencontrée pendant les essais de lecture.

    if not path.exists():#vérifie si le fichier existe.
        raise FileNotFoundError(f"Fichier introuvable : {path}")
       # Ce bloc teste toutes les combinaisons possibles. avec encodage et separateur pour trouver automatiquement la bonne combinaison.
    for encoding in encodings:#Cette boucle parcourt tous les encodages possibles.
        for sep in separators:#Pour chaque encodage, le programme teste aussi chaque séparateur.
            try:
                df = pd.read_csv(
                    path,
                    encoding=encoding,
                    sep=sep,
                    engine="python" #demande à pandas d’utiliser le moteur Python pour lire le CSV plus flexible
                )

                if df.shape[1] > 1:#Cette condition vérifie si le fichier a été lu avec plus d’une colonne;Parce qu’un CSV mal lu peut donner une seule grande colonne au lieu de plusieurs colonnes.
                    print(
                        f"Lecture réussie : {path.name} | "
                        f"encoding={encoding} | sep='{sep}' | "
                        f"lignes={df.shape[0]} | colonnes={df.shape[1]}"
                    )
                    return df
            #Si une combinaison ne fonctionne pas, l’erreur est récupérée dans last_error.(Je garde l’erreur dans last_error et je teste la combinaison suivante.)
            except Exception as exc:
                last_error = exc

    raise RuntimeError(
        f"Impossible de lire correctement le fichier {path}. "
        f"Dernière erreur : {last_error}"
    )


def read_excel_safely(path: Path) -> pd.DataFrame:
    """
    Lecture sécurisée d'un fichier Excel: lire le fichier sans planter directement et avec des vérifications.
    
    df.shape retourne deux valeurs : (nombre_de_lignes, nombre_de_colonnes)
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

    print_dataset_info("Base population client", pop_df)
    print_dataset_info("Base SOS Solde", sos_df)

    print("\n" + "=" * 80)
    print("Vérification terminée avec succès.")
    print("=" * 80)


if __name__ == "__main__":
    main()
