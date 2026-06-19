# Plateforme interne Tunisie Telecom

Application web interne composée d'un frontend React/Vite et d'un backend FastAPI.
Elle couvre l'authentification sécurisée, la MFA/TOTP, la gestion des utilisateurs et
départements, les tableaux de bord Power BI, les traitements ELT et le module Bad
Debts avec import de données, scoring, agent d'aide à la décision et génération de
rapports.

## Structure du projet

```text
.
|-- backend/              # API FastAPI, logique métier, modèles, migrations
|-- frontend/             # Interface React/Vite
|-- machine_learning/     # Données, notebook, scripts et rapports ML
|-- n8n/                  # Workflows et configuration n8n
|-- figures/              # Schémas et figures de documentation
`-- README.md
```

Les dossiers de cache, d'environnement local, de logs, de backups PostgreSQL et de
résultats générés ne doivent pas être versionnés (`.venv/`, `backend/venv/`,
`frontend/dist/`, `backend/runtime_data/`, `postgres18_data_BACKUP_DO_NOT_DELETE/`,
`__pycache__/`, `*.pyc`, `.env`, etc.).

## Prérequis

- Python 3.11 ou plus récent
- Node.js 20 ou plus récent
- PostgreSQL
- Un environnement virtuel Python
- Optionnel : Ollama pour les fonctions LLM du module Bad Debts

## Backend

Le backend est une API FastAPI basée sur SQLAlchemy, Alembic et PostgreSQL. Il expose
les modules d'authentification, MFA/TOTP, administration, sécurité du compte, ELT,
n8n et Bad Debts.

### Installation

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Sur Linux/macOS :

```bash
source venv/bin/activate
```

### Configuration

Créer un fichier `backend/.env` et l'adapter à l'environnement local :

```env
APP_NAME=Tunisie Telecom Backend
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/tt_internal_platform

JWT_SECRET_KEY=CHANGE_THIS_SECRET_KEY_WITH_LONG_RANDOM_VALUE
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

FRONTEND_BASE_URL=http://localhost:5173
BACKEND_PUBLIC_BASE_URL=http://127.0.0.1:8000

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=
SMTP_FROM_NAME=Tunisie Telecom Platform
SMTP_USE_TLS=true
MAIL_DEBUG_MODE=true

PASSWORD_MIN_LENGTH=12
PASSWORD_MAX_LENGTH=64

ACTIVATION_FIRST_TOKEN_EXPIRE_MINUTES=30
ACTIVATION_TOKEN_EXPIRE_MINUTES=15
PASSWORD_RESET_TOKEN_EXPIRE_MINUTES=15
MFA_PENDING_EXPIRE_MINUTES=5

TOTP_ENCRYPTION_KEY=GENERATE_A_FERNET_KEY
TOTP_ISSUER_NAME=Tunisie Telecom Platform

WEBAUTHN_ORIGIN=http://localhost:5173
WEBAUTHN_RP_ID=localhost
WEBAUTHN_RP_NAME=Tunisie Telecom Platform
WEBAUTHN_TIMEOUT_MS=60000
ADMIN_WEBAUTHN_ACTION_EXPIRE_MINUTES=5

ENABLE_LLM_AGENT=false
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
LLM_TIMEOUT_SECONDS=12
LLM_MAX_TOKENS=220
N8N_API_KEY=

BAD_DEBTS_LLM_PROVIDER=ollama
BAD_DEBTS_OLLAMA_BASE_URL=http://127.0.0.1:11434
BAD_DEBTS_OLLAMA_MODEL=qwen2.5:3b
BAD_DEBTS_OLLAMA_BACKUP_MODEL=qwen2.5:7b
BAD_DEBTS_OLLAMA_TIMEOUT_SECONDS=60
BAD_DEBTS_OLLAMA_TEMPERATURE=0.1
BAD_DEBTS_OLLAMA_NUM_PREDICT=260
BAD_DEBTS_OLLAMA_KEEP_ALIVE=10m
BAD_DEBTS_OLLAMA_NUM_CTX=2048
BAD_DEBTS_OLLAMA_ENABLED=true
BAD_DEBTS_ENABLE_CLIENT_REPORT=true
```

Ne pas versionner les vrais secrets SMTP, JWT, TOTP, les clés API ou les chaînes de
connexion de production.

Pour générer une clé Fernet compatible avec `TOTP_ENCRYPTION_KEY` :

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Base de données et migrations

```bash
cd backend
alembic upgrade head
```

Pour créer ou mettre à jour le compte super administrateur de développement :

```bash
python create_super_admin.py
```

Vérifier les identifiants dans `create_super_admin.py` avant toute utilisation hors
développement.

### Lancement

```bash
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Endpoints utiles :

- API : `http://127.0.0.1:8000`
- Documentation Swagger : `http://127.0.0.1:8000/docs`
- Health check base de données : `http://127.0.0.1:8000/health/db`

### Modules backend

- `app/main.py` : création de l'application FastAPI, CORS et inclusion des routes
- `app/api/routes/` : routes HTTP
- `app/services/` : logique métier
- `app/models/` : modèles SQLAlchemy
- `app/schemas/` : schémas Pydantic
- `app/db/` : configuration de la base de données
- `app/core/` : configuration, constantes et sécurité
- `app/agents/` : agent IA/LLM pour Bad Debts
- `migrations/` : migrations Alembic et scripts SQL

Routes principales :

- `/auth/*` : connexion, MFA, TOTP, codes de secours, activation et reset mot de passe
- `/admin/*` : gestion utilisateurs, départements, droits et rôles
- `/auth/security/*` : sécurité du compte et signalements
- `/elt/*` : traitements ELT, surveillance, archives et téléchargements
- `/n8n/*` : intégrations n8n
- `/api/v1/bad-debts/*` : imports, clients à risque, rapports et agent Bad Debts

## Frontend

Le frontend est une application React avec Vite, React Router, Axios et Lucide React.

### Installation

```bash
cd frontend
npm install
```

### Configuration

Créer ou compléter `frontend/.env` :

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_POWERBI_DASHBOARD_SERVICE_SOS_URL=
VITE_POWER_BI_PARC_URL=
```

Les variables commençant par `VITE_` sont exposées au navigateur. Ne pas y placer de
secret.

### Lancement

```bash
cd frontend
npm run dev
```

Par défaut, Vite démarre sur :

```text
http://localhost:5173
```

Si le port est déjà utilisé, Vite choisit un autre port. Le backend autorise déjà
plusieurs ports de développement courants (`5173` à `5176`).

### Scripts disponibles

```bash
npm run dev       # serveur de développement
npm run build     # build de production
npm run preview   # prévisualisation du build
npm run lint      # analyse ESLint
```

### Modules frontend

- `src/main.jsx` : point d'entrée React
- `src/App.jsx` : déclaration des routes
- `src/api/api.js` : client Axios et helpers API
- `src/context/AuthContext.jsx` : état d'authentification global
- `src/components/ProtectedRoute.jsx` : protection des routes par rôle/droit
- `src/components/Layout.jsx` : layout principal
- `src/pages/` : pages fonctionnelles de l'application
- `src/styles/` : styles globaux et styles des dashboards

Pages principales :

- Authentification : login, TOTP, MFA, codes de secours
- Activation et réinitialisation du mot de passe
- Accueil utilisateur
- Administration utilisateurs, départements et droits
- Tableau de bord ELT
- Dashboards Power BI Service SOS et Parc Service SOS
- Dashboard Bad Debts
- Sécurité du compte et signalement d'incidents

## Machine Learning et Bad Debts

Le dossier `machine_learning/` contient le pipeline de préparation et segmentation :

- `scripts/00_check_datasets.py` : vérification des fichiers source
- `scripts/01_build_merged_dataset.py` : construction du dataset fusionné
- `scripts/02_data_quality_audit.py` : audit qualité
- `scripts/03_validate_clients_segmented.py` : validation de l'export segmenté
- `scripts/run_notebook.py` : exécution automatisée du notebook
- `notebooks/ml_clustering_baddebts.ipynb` : notebook de clustering

Le backend peut lancer ce pipeline via le module Bad Debts et écrire les résultats
dans `backend/runtime_data/`. Ces résultats sont des artefacts d'exécution et ne
devraient pas être commités.

## ELT

La configuration ELT se trouve dans `backend/app/core/elt_config.py`. Elle pointe vers
un projet ELT externe local. Adapter les chemins de ce fichier avant d'utiliser les
routes `/elt/*` sur une autre machine.

## Démarrage complet en local

1. Démarrer PostgreSQL et créer la base cible.
2. Configurer `backend/.env`.
3. Installer les dépendances backend puis appliquer les migrations.
4. Lancer l'API FastAPI sur le port `8000`.
5. Configurer `frontend/.env`.
6. Installer les dépendances frontend.
7. Lancer Vite et ouvrir `http://localhost:5173`.

Exemple :

```bash
# Terminal 1
cd backend
venv\Scripts\activate
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2
cd frontend
npm run dev
```

## Tests et vérification

Backend :

```bash
cd backend
python scripts/test_bad_debts_contact_validation.py
python scripts/test_bad_debts_global_reports.py
```

Frontend :

```bash
cd frontend
npm run lint
npm run build
```

## Sécurité

- Remplacer les secrets de développement avant un déploiement.
- Ne jamais commiter les fichiers `.env`.
- Utiliser une clé `JWT_SECRET_KEY` longue et aléatoire.
- Générer une vraie clé `TOTP_ENCRYPTION_KEY`.
- Vérifier les identifiants du super administrateur avant toute mise en production.
- Désactiver `MAIL_DEBUG_MODE` en production.
- Ne pas versionner les dossiers de données générées, logs, backups de base ou caches.

## Déploiement

Backend :

```bash
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Frontend :

```bash
cd frontend
npm install
npm run build
```

Le dossier `frontend/dist` contient les fichiers statiques à servir avec Nginx, Apache
ou un service d'hébergement frontend.
