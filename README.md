# Plateforme interne Tunisie Telecom

Application web interne composee d'un frontend React/Vite et d'un backend FastAPI. Le projet couvre l'authentification securisee, la gestion des utilisateurs et departements, les tableaux de bord Power BI, les traitements ELT et le module Bad Debts avec import de donnees, scoring et generation de rapports.

## Structure du projet

```text
.
|-- backend/              # API FastAPI, logique metier, base de donnees, migrations
|-- frontend/             # Interface React/Vite
|-- machine_learning/     # Donnees, notebooks, scripts et rapports ML
|-- n8n/                  # Elements lies aux workflows n8n
`-- README.md
```

## Prerequis

- Python 3.11 ou plus recent
- Node.js 20 ou plus recent
- PostgreSQL
- Un environnement virtuel Python
- Optionnel : Ollama ou OpenAI pour les fonctions LLM du module Bad Debts

## Backend

Le backend est une API FastAPI basee sur SQLAlchemy, Alembic et PostgreSQL. Il expose les modules d'authentification, MFA/TOTP, administration, securite compte, ELT et Bad Debts.

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

Creer un fichier `backend/.env` a partir des variables suivantes :

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

USER_SESSION_IDLE_MINUTES=20
ADMIN_SESSION_IDLE_MINUTES=15

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

BAD_DEBTS_LLM_PROVIDER=ollama
BAD_DEBTS_OLLAMA_BASE_URL=http://127.0.0.1:11434
BAD_DEBTS_OLLAMA_MODEL=qwen2.5:3b
BAD_DEBTS_OLLAMA_BACKUP_MODEL=qwen2.5:7b
BAD_DEBTS_OLLAMA_TIMEOUT_SECONDS=60
BAD_DEBTS_OLLAMA_ENABLED=true
BAD_DEBTS_ENABLE_CLIENT_REPORT=true
```

Ne pas versionner les vrais secrets SMTP, JWT, TOTP ou les chaines de connexion de production.

### Base de donnees et migrations

```bash
cd backend
alembic upgrade head
```

Pour creer ou mettre a jour le compte super administrateur de developpement :

```bash
python create_super_admin.py
```

Verifier les identifiants dans `create_super_admin.py` avant toute utilisation hors developpement.

### Lancement

```bash
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Endpoints utiles :

- API : `http://127.0.0.1:8000`
- Documentation Swagger : `http://127.0.0.1:8000/docs`
- Health check base de donnees : `http://127.0.0.1:8000/health/db`

### Principaux modules backend

- `app/main.py` : creation de l'application FastAPI, CORS et inclusion des routes
- `app/api/routes/` : routes HTTP
- `app/services/` : logique metier
- `app/models/` : modeles SQLAlchemy
- `app/schemas/` : schemas Pydantic
- `app/db/` : configuration de la base de donnees
- `app/core/` : configuration, constantes et securite
- `app/agents/` : agent IA/LLM pour Bad Debts
- `migrations/` : migrations Alembic et scripts SQL

Routes principales :

- `/auth/*` : connexion, MFA, TOTP, codes de secours, activation et reset mot de passe
- `/admin/*` : gestion utilisateurs, departements, droits et roles
- `/auth/security/*` : securite du compte et signalements
- `/elt/*` : traitements ELT, surveillance, archives et telechargements
- `/api/v1/bad-debts/*` : imports, clients a risque, rapports et agent Bad Debts

## Frontend

Le frontend est une application React avec Vite, React Router, Axios et Lucide React.

### Installation

```bash
cd frontend
npm install
```

### Configuration

Creer ou completer `frontend/.env` :

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_POWERBI_DASHBOARD_SERVICE_SOS_URL=
VITE_POWER_BI_PARC_URL=
```

Les variables commencant par `VITE_` sont exposees au navigateur. Ne pas y placer de secret.

### Lancement

```bash
cd frontend
npm run dev
```

Par defaut, Vite demarre sur :

```text
http://localhost:5173
```

Si le port est deja utilise, Vite choisit un autre port. Le backend autorise deja plusieurs ports de developpement courants (`5173` a `5176`).

### Scripts disponibles

```bash
npm run dev       # serveur de developpement
npm run build     # build de production
npm run preview   # previsualisation du build
npm run lint      # analyse ESLint
```

### Principaux modules frontend

- `src/main.jsx` : point d'entree React
- `src/App.jsx` : declaration des routes
- `src/api/api.js` : client Axios et helpers API
- `src/context/AuthContext.jsx` : etat d'authentification global
- `src/components/ProtectedRoute.jsx` : protection des routes par role/droit
- `src/components/Layout.jsx` : layout principal
- `src/pages/` : pages fonctionnelles de l'application
- `src/styles/` : styles globaux et styles des dashboards

Pages principales :

- Authentification : login, TOTP, MFA, codes de secours
- Activation et reinitialisation du mot de passe
- Accueil utilisateur
- Administration utilisateurs/departements/droits
- Tableau de bord ELT
- Dashboards Power BI Service SOS et Parc Service SOS
- Dashboard Bad Debts
- Securite du compte et signalement d'incidents

## Demarrage complet en local

1. Demarrer PostgreSQL et creer la base cible.
2. Configurer `backend/.env`.
3. Installer les dependances backend puis appliquer les migrations.
4. Lancer l'API FastAPI sur le port `8000`.
5. Configurer `frontend/.env`.
6. Installer les dependances frontend.
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

## Tests et verification

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

## Notes de securite

- Remplacer les secrets de developpement avant un deploiement.
- Ne jamais commiter les fichiers `.env`.
- Utiliser une cle `JWT_SECRET_KEY` longue et aleatoire.
- Generer une vraie cle `TOTP_ENCRYPTION_KEY`.
- Verifier les identifiants du super administrateur avant toute mise en production.
- Desactiver `MAIL_DEBUG_MODE` en production.

## Deploiement

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

Le dossier `frontend/dist` contient les fichiers statiques a servir avec Nginx, Apache ou un service d'hebergement frontend.
