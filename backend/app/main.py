from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

import app.models

from app.api.routes.account_security import router as account_security_router
from app.api.routes.activation import router as activation_router
from app.api.routes.admin import router as admin_router
from app.api.routes.admin_departements import router as admin_departements_router
from app.api.routes.auth import router as auth_router
from app.api.routes.bad_debts import router as bad_debts_router
from app.api.routes.n8n import router as n8n_router
from app.api.routes.elt import router as elt_router
from app.api.routes.password_reset import router as password_reset_router
from app.api.routes.security import router as security_router
from app.core.config import settings
from app.db.database import engine


DEV_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:5175",
    "http://127.0.0.1:5175",
    "http://localhost:5176",
    "http://127.0.0.1:5176",
]


def _cors_origins() -> list[str]:
    origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        *DEV_CORS_ORIGINS,
        settings.FRONTEND_BASE_URL,
    ]
    return list(dict.fromkeys(origin.rstrip("/") for origin in origins if origin))


app = FastAPI(
    title="Tunisie Telecom Backend",
    description=(
        "Plateforme interne Tunisie Telecom - Authentification TOTP + Admin + ELT"
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "success": True,
        "message": "Backend FastAPI Tunisie Telecom démarré avec succès.",
    }


@app.get("/health/db")
def health_db():
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            value = result.scalar()

        return {
            "success": True,
            "message": "Connexion PostgreSQL réussie.",
            "result": value,
        }

    except Exception as exc:
        return {
            "success": False,
            "message": "Échec connexion PostgreSQL.",
            "error": str(exc),
        }


app.include_router(auth_router)
app.include_router(activation_router)
app.include_router(password_reset_router)
app.include_router(admin_router)
app.include_router(admin_departements_router)
app.include_router(account_security_router)
app.include_router(security_router)
app.include_router(elt_router)
app.include_router(bad_debts_router)
app.include_router(n8n_router)
