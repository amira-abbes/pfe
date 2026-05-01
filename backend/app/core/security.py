from datetime import datetime, timedelta, timezone
import hashlib
import secrets

from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str | None) -> bool:
    if not plain_password or not hashed_password:
        return False

    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False


def generate_secure_token(length: int = 48) -> str:
    return secrets.token_urlsafe(length)


def generate_numeric_code(length: int = 10) -> str:
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_activation_token(token: str) -> str:
    return hash_token(token)


def hash_session_token(token: str) -> str:
    return hash_token(token)


def normalize_recovery_code(code: str) -> str:
    return str(code or "").strip().replace(" ", "").replace("-", "").upper()


def hash_recovery_code(code: str) -> str:
    return hash_token(normalize_recovery_code(code))


def generate_raw_session_token() -> str:
    return generate_secure_token(48)


def generate_raw_activation_token() -> str:
    return generate_secure_token(48)


def generate_raw_password_reset_token() -> str:
    return generate_secure_token(48)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    payload = data.copy()
    expire = utc_now() + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    payload.update(
        {
            "exp": expire,
            "type": "access",
        }
    )

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError as exc:
        raise ValueError("Token invalide ou expiré") from exc

    if payload.get("type") != "access":
        raise ValueError("Type de token invalide")

    return payload


def create_scoped_token(
    data: dict,
    purpose: str,
    expires_delta: timedelta | None = None,
) -> str:
    payload = data.copy()
    expire = utc_now() + (expires_delta or timedelta(minutes=10))

    payload.update(
        {
            "exp": expire,
            "purpose": purpose,
            "type": "scoped",
        }
    )

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_scoped_token(token: str, expected_purpose: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError as exc:
        raise ValueError("Token invalide ou expiré") from exc

    if payload.get("type") != "scoped":
        raise ValueError("Type de token invalide")

    if payload.get("purpose") != expected_purpose:
        raise ValueError("Portée de token invalide")

    return payload


def get_fernet() -> Fernet:
    return Fernet(settings.TOTP_ENCRYPTION_KEY.encode("utf-8"))


def encrypt_secret(value: str) -> str:
    return get_fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None

    raw = str(value)

    try:
        return get_fernet().decrypt(raw.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return raw