import re

from app.core.config import settings
from app.core.security import verify_password


class PasswordPolicyService:
    def validate(
        self,
        password: str,
        confirm_password: str,
        email: str,
        nom_complet: str,
        old_password_hash: str | None = None,
    ) -> None:
        if password != confirm_password:
            raise ValueError("Les mots de passe ne correspondent pas.")

        if len(password) < settings.PASSWORD_MIN_LENGTH:
            raise ValueError(self._generic_message())

        if len(password) > settings.PASSWORD_MAX_LENGTH:
            raise ValueError(
                f"Le mot de passe ne doit pas dépasser {settings.PASSWORD_MAX_LENGTH} caractères."
            )

        if not any(c.isupper() for c in password):
            raise ValueError(self._generic_message())

        if not any(c.islower() for c in password):
            raise ValueError(self._generic_message())

        if not any(c.isdigit() for c in password):
            raise ValueError(self._generic_message())

        if not any(not c.isalnum() for c in password):
            raise ValueError(self._generic_message())

        lowered_password = password.casefold()
        email_value = str(email or "").casefold()
        email_local = email_value.split("@")[0]

        if email_value and email_value in lowered_password:
            raise ValueError("Le mot de passe ne doit pas contenir votre adresse email.")

        if email_local and len(email_local) >= 3 and email_local in lowered_password:
            raise ValueError("Le mot de passe ne doit pas contenir votre adresse email.")

        for token in self._name_tokens(nom_complet):
            if token in lowered_password:
                raise ValueError("Le mot de passe ne doit pas contenir votre nom ou prénom.")

        if old_password_hash and verify_password(password, old_password_hash):
            raise ValueError("Le nouveau mot de passe doit être différent de l'ancien mot de passe.")

    def _name_tokens(self, nom_complet: str) -> list[str]:
        return [
            part.casefold()
            for part in re.split(r"[\s._\-@]+", nom_complet or "")
            if len(part) >= 3
        ]

    def _generic_message(self) -> str:
        return (
            "Le mot de passe doit contenir au minimum 12 caractères, "
            "une majuscule, une minuscule, un chiffre et un symbole."
        )