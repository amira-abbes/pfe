from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Tunisie Telecom Backend"

    DATABASE_URL: str

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    FRONTEND_BASE_URL: str = "http://localhost:5173"
    BACKEND_PUBLIC_BASE_URL: str = "http://127.0.0.1:8000"

    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_FROM_NAME: str = "Tunisie Telecom Platform"
    SMTP_USE_TLS: bool = True
    MAIL_DEBUG_MODE: bool = True

    PASSWORD_MIN_LENGTH: int = 12
    PASSWORD_MAX_LENGTH: int = 64

    # Premier lien envoyé par l'admin après création utilisateur
    ACTIVATION_FIRST_TOKEN_EXPIRE_MINUTES: int = 30

    # Liens redemandés par l'utilisateur après expiration/invalidation
    ACTIVATION_TOKEN_EXPIRE_MINUTES: int = 15

    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 15

    MFA_PENDING_EXPIRE_MINUTES: int = 5

    USER_SESSION_IDLE_MINUTES: int = 20
    ADMIN_SESSION_IDLE_MINUTES: int = 15

    TOTP_ENCRYPTION_KEY: str
    TOTP_ISSUER_NAME: str = "Tunisie Telecom Platform"

    WEBAUTHN_ORIGIN: str = "http://localhost:5173"
    WEBAUTHN_RP_ID: str = "localhost"
    WEBAUTHN_RP_NAME: str = "Tunisie Telecom Platform"
    WEBAUTHN_TIMEOUT_MS: int = 60000

    ADMIN_WEBAUTHN_ACTION_EXPIRE_MINUTES: int = 5

    ENABLE_LLM_AGENT: bool = False
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    LLM_TIMEOUT_SECONDS: int = 12
    LLM_MAX_TOKENS: int = 220
    N8N_API_KEY: str | None = None

    BAD_DEBTS_LLM_PROVIDER: str = "ollama"
    BAD_DEBTS_OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    BAD_DEBTS_OLLAMA_MODEL: str = "qwen2.5:3b"
    BAD_DEBTS_OLLAMA_BACKUP_MODEL: str | None = "qwen2.5:7b"
    BAD_DEBTS_OLLAMA_TIMEOUT_SECONDS: int = 60
    BAD_DEBTS_OLLAMA_TEMPERATURE: float = 0.1
    BAD_DEBTS_OLLAMA_NUM_PREDICT: int = 260
    BAD_DEBTS_OLLAMA_KEEP_ALIVE: str = "10m"
    BAD_DEBTS_OLLAMA_NUM_CTX: int = 2048
    BAD_DEBTS_OLLAMA_ENABLED: bool = True
    BAD_DEBTS_ENABLE_CLIENT_REPORT: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=True,
    )


settings = Settings()
