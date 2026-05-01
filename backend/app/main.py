from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

import app.models

from app.api.routes.account_security import router as account_security_router
from app.api.routes.activation import router as activation_router
from app.api.routes.admin import router as admin_router
from app.api.routes.admin_departements import router as admin_departements_router
from app.api.routes.admin_sensitive import router as admin_sensitive_router
from app.api.routes.auth import router as auth_router
from app.api.routes.password_reset import router as password_reset_router
from app.api.routes.security import router as security_router
from app.db.database import engine


app = FastAPI(
    title="Tunisie Telecom Backend",
    description=(
        "Plateforme interne Tunisie Telecom - Authentification TOTP + Admin + "
        "Actions sensibles WebAuthn"
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=False,
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
app.include_router(admin_sensitive_router)
app.include_router(account_security_router)
app.include_router(security_router)