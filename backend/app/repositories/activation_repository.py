from sqlalchemy.orm import Session, selectinload

from app.models.jeton_activation import JetonActivation
from app.models.journal_audit import JournalAudit
from app.models.utilisateur import Utilisateur


class ActivationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_activation_token_by_hash(self, token_hash: str) -> JetonActivation | None:
        return (
            self.db.query(JetonActivation)
            .options(selectinload(JetonActivation.utilisateur))
            .filter(JetonActivation.jeton_hash == token_hash)
            .filter(JetonActivation.type_jeton == "ACCOUNT_ACTIVATION")
            .first()
        )

    def save_user(self, user: Utilisateur) -> None:
        self.db.add(user)
        self.db.flush()

    def save_token(self, token: JetonActivation) -> None:
        self.db.add(token)
        self.db.flush()

    def add_audit(
        self,
        action: str,
        acteur_id=None,
        cible_id=None,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
        niveau_risque: str = "FAIBLE",
        details: dict | None = None,
    ) -> None:
        self.db.add(
            JournalAudit(
                utilisateur_acteur_id=acteur_id,
                cible_utilisateur_id=cible_id,
                action_effectuee=action,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                niveau_risque=niveau_risque,
                details=details or {},
            )
        )
        self.db.flush()

    def commit(self):
        self.db.commit()

    def rollback(self):
        self.db.rollback()