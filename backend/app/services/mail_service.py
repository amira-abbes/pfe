import html
import re
import smtplib
from email.header import Header
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import ensure_aware_utc, utc_now
from app.models.notification_securite import NotificationSecurite
from app.models.utilisateur import Utilisateur
from app.services.mail_templates.account import (
    activation_email,
    password_reset_email,
    plain_activation,
    plain_password_reset,
    plain_recovery_codes,
    recovery_codes_email,
)
from app.services.mail_templates.base import (
    action_button,
    clean_email_content,
    multiline_html,
    render_layout,
)
from app.services.mail_templates.security import (
    admin_password_lockout_email,
    lockout_security_email,
    plain_admin_password_lockout,
    plain_lockout_security,
    plain_security_alert,
    security_alert_email,
)


class MailService:
    def _sanitize_email_content(self, value: str) -> str:
        cleaned = clean_email_content(value)
        cleaned = re.sub(
            r"<(p|div|span)\b[^>]*>\s*(?:\.{3}|…|&hellip;)\s*</\1>",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"(?m)^\s*(?:\.{3}|…|&hellip;)\s*$", "", cleaned)
        return cleaned.strip()

    def _safe(self, value: str) -> str:
        return html.escape(str(value), quote=True)

    def format_user_agent(self, user_agent: str | None) -> str:
        raw = str(user_agent or "").strip()
        value = raw.lower()

        if not value:
            return "Non disponible"

        known = {
            "google chrome": "Google Chrome",
            "microsoft edge": "Microsoft Edge",
            "mozilla firefox": "Mozilla Firefox",
            "safari": "Safari",
            "opera": "Opera",
            "navigateur sur windows": "Navigateur sur Windows",
            "navigateur sur android": "Navigateur sur Android",
            "navigateur sur ios": "Navigateur sur iOS",
        }

        if value in known:
            return known[value]
        if "edg/" in value or "edge/" in value:
            return "Microsoft Edge"
        if "opr/" in value or "opera" in value:
            return "Opera"
        if "firefox/" in value:
            return "Mozilla Firefox"
        if "chrome/" in value or "crios/" in value:
            return "Google Chrome"
        if "safari/" in value and "chrome/" not in value:
            return "Safari"
        if "windows" in value:
            return "Navigateur sur Windows"
        if "android" in value:
            return "Navigateur sur Android"
        if "iphone" in value or "ipad" in value:
            return "Navigateur sur iOS"

        return "Navigateur inconnu"

    def format_datetime_for_email(self, value=None) -> str:
        try:
            local_dt = ensure_aware_utc(value or utc_now()).astimezone(
                ZoneInfo("Africa/Tunis")
            )
            return local_dt.strftime("%d/%m/%Y %H:%M:%S")
        except Exception:
            return str(value or "").replace("UTC", "").strip()

    def _find_frontend_public_asset(self, filename: str) -> Path | None:
        candidates = [
            Path.cwd() / "frontend" / "public" / filename,
            Path.cwd().parent / "frontend" / "public" / filename,
            Path.cwd() / "public" / filename,
            Path(__file__).resolve().parents[3] / "frontend" / "public" / filename,
        ]
        return next((path for path in candidates if path.exists() and path.is_file()), None)

    def _attach_inline_image(
        self,
        message: MIMEMultipart,
        filename: str,
        content_id: str,
    ) -> None:
        path = self._find_frontend_public_asset(filename)
        if not path:
            return

        try:
            with open(path, "rb") as file:
                image = MIMEImage(file.read())
            image.add_header("Content-ID", f"<{content_id}>")
            image.add_header("Content-Disposition", "inline")
            image.add_header("X-Attachment-Id", content_id)
            message.attach(image)
        except Exception:
            return

    def _attach_inline_images(self, message: MIMEMultipart, include_background: bool = False) -> None:
        self._attach_inline_image(message, "tt-logo.png", "tt_logo")

    def _send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str,
        attach_background: bool = False,
    ) -> bool:
        subject = self._sanitize_email_content(subject)
        html_body = self._sanitize_email_content(html_body)
        text_body = self._sanitize_email_content(text_body)

        if settings.MAIL_DEBUG_MODE:
            print("\n========== MAIL DEBUG MODE ==========")
            print(f"TO: {to_email}")
            print(f"SUBJECT: {subject}")
            print(text_body)
            print("====================================\n")
            return True

        msg = MIMEMultipart("related")
        msg["Subject"] = str(Header(subject, "utf-8"))
        msg["From"] = f"{str(Header(settings.SMTP_FROM_NAME, 'utf-8'))} <{settings.SMTP_FROM_EMAIL}>"
        msg["To"] = to_email

        alternative = MIMEMultipart("alternative")
        alternative.attach(MIMEText(text_body, "plain", "utf-8"))
        alternative.attach(MIMEText(html_body, "html", "utf-8"))
        msg.attach(alternative)

        self._attach_inline_images(msg, include_background=attach_background)

        timeout = getattr(settings, "SMTP_TIMEOUT_SECONDS", 20)
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=timeout) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_FROM_EMAIL, [to_email], msg.as_string())

        return True

    def _record_notification(
        self,
        db: Session | None,
        utilisateur_id,
        type_notification: str,
        email_destinataire: str,
        sujet: str,
        statut: str,
        erreur_envoi: str | None = None,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
        details: dict | None = None,
    ) -> None:
        if db is None or utilisateur_id is None:
            return

        db.add(
            NotificationSecurite(
                utilisateur_id=utilisateur_id,
                type_notification=type_notification,
                email_destinataire=email_destinataire,
                sujet=sujet,
                statut=statut,
                erreur_envoi=erreur_envoi,
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                details=details or {},
                date_envoi=utc_now() if statut == "ENVOYE" else None,
            )
        )
        db.flush()

    def send_activation_link_email(
        self,
        to_email: str,
        activation_link: str,
        expire_minutes: int = 15,
        db: Session | None = None,
        utilisateur_id=None,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
    ) -> bool:
        subject = "Activation de votre compte - Plateforme interne"
        html_body = activation_email(activation_link, expire_minutes)
        text_body = plain_activation(activation_link, expire_minutes)

        return self._send_and_record(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            db=db,
            utilisateur_id=utilisateur_id,
            type_notification="ACCOUNT_ACTIVATION",
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            debug_details={"activation_link": activation_link},
        )

    def send_password_reset_email(
        self,
        to_email: str,
        reset_link: str,
        expire_minutes: int = 15,
        from_lockout: bool = False,
        db: Session | None = None,
        utilisateur_id=None,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
    ) -> bool:
        subject = (
            "Récupération de votre accès après blocage"
            if from_lockout
            else "Réinitialisation de votre mot de passe"
        )
        html_body = password_reset_email(reset_link, expire_minutes, from_lockout)
        text_body = plain_password_reset(reset_link, expire_minutes)

        return self._send_and_record(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            db=db,
            utilisateur_id=utilisateur_id,
            type_notification=(
                "PASSWORD_RESET_FROM_LOCKOUT" if from_lockout else "PASSWORD_RESET"
            ),
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            debug_details={"reset_link": reset_link},
        )

    def send_security_alert_email(
        self,
        to_email: str,
        subject: str,
        message: str,
        action_link: str | None = None,
        action_label: str = "Ouvrir le lien sécurisé",
        db: Session | None = None,
        utilisateur_id=None,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
        details: dict | None = None,
    ) -> bool:
        html_body = security_alert_email("Alerte de sécurité", message, action_link, action_label)
        text_body = plain_security_alert(message, action_link)

        return self._send_and_record(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            db=db,
            utilisateur_id=utilisateur_id,
            type_notification="SECURITY_ALERT",
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            details=details or {},
            attach_background=True,
        )

    def send_password_changed_email(
        self,
        to_email: str,
        db: Session | None = None,
        utilisateur_id=None,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
    ) -> bool:
        return self.send_security_alert_email(
            to_email=to_email,
            subject="Confirmation de changement de mot de passe",
            message=(
                "Votre mot de passe a été modifié avec succès. "
                "Si vous n’êtes pas à l’origine de cette action, contactez immédiatement l’administrateur."
            ),
            db=db,
            utilisateur_id=utilisateur_id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            details={"type": "PASSWORD_CHANGED"},
        )

    def send_recovery_codes_email(
        self,
        to_email: str,
        recovery_codes: list[str],
        db: Session | None = None,
        utilisateur_id=None,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
        role: str | None = None,
        details: dict | None = None,
    ) -> bool:
        subject = "Codes de secours régénérés"
        role = role or self._get_user_role(db, utilisateur_id)
        html_body = recovery_codes_email(recovery_codes, role=role)
        text_body = plain_recovery_codes(recovery_codes, role=role)

        notification_details = {
            "count": len(recovery_codes),
            **(details or {}),
        }

        return self._send_and_record(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            db=db,
            utilisateur_id=utilisateur_id,
            type_notification="RECOVERY_CODES_SENT",
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            details=notification_details,
            attach_background=True,
        )

    def _get_user_role(self, db: Session | None, utilisateur_id) -> str | None:
        if db is None or utilisateur_id is None:
            return None
        user = db.query(Utilisateur).filter(Utilisateur.id == utilisateur_id).first()
        return str(user.role or "").upper() if user else None

    def send_lockout_security_email(
        self,
        to_email: str,
        reset_link: str,
        report_link: str,
        ip_address: str,
        user_agent_value: str,
        detected_at: str,
        reset_link_expire_minutes: int = 15,
        report_link_expire_hours: int = 24,
        db: Session | None = None,
        utilisateur_id=None,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
    ) -> bool:
        subject = "Alerte de sécurité - compte temporairement bloqué"
        browser_label = user_agent_value or self.format_user_agent(user_agent)
        clean_detected_at = str(detected_at or "").replace("UTC", "").strip()

        html_body = lockout_security_email(
            reset_link=reset_link,
            report_link=report_link,
            ip_address=ip_address,
            browser_label=browser_label,
            detected_at=clean_detected_at,
            reset_link_expire_minutes=reset_link_expire_minutes,
            report_link_expire_hours=report_link_expire_hours,
        )
        text_body = plain_lockout_security(
            reset_link=reset_link,
            report_link=report_link,
            ip_address=ip_address,
            browser_label=browser_label,
            detected_at=clean_detected_at,
            reset_link_expire_minutes=reset_link_expire_minutes,
            report_link_expire_hours=report_link_expire_hours,
        )

        details = {
            "ip": ip_address,
            "user_agent": browser_label,
            "detected_at": clean_detected_at,
            "reset_link_expire_minutes": reset_link_expire_minutes,
            "report_link_expire_hours": report_link_expire_hours,
        }
        debug_details = {
            **details,
            "reset_link": reset_link,
            "report_link": report_link,
        }

        return self._send_and_record(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            db=db,
            utilisateur_id=utilisateur_id,
            type_notification="PASSWORD_LOCKOUT_SECURITY_ALERT",
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            details=details,
            debug_details=debug_details,
            attach_background=True,
        )

    def send_admin_password_lockout_email(
        self,
        to_email: str,
        reset_link: str,
        report_link: str,
        ip_address: str,
        user_agent_value: str,
        detected_at: str,
        reset_link_expire_minutes: int = 15,
        report_link_expire_hours: int = 24,
        db: Session | None = None,
        utilisateur_id=None,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
    ) -> bool:
        subject = "Alerte de sécurité - compte administrateur temporairement bloqué"
        expire_minutes = int(reset_link_expire_minutes or 15)
        browser_label = user_agent_value or self.format_user_agent(user_agent)
        clean_detected_at = str(detected_at or "").replace("UTC", "").strip()
        html_body = admin_password_lockout_email(
            reset_link=reset_link,
            report_link=report_link,
            ip_address=ip_address,
            browser_label=browser_label,
            detected_at=clean_detected_at,
            reset_link_expire_minutes=expire_minutes,
            report_link_expire_hours=int(report_link_expire_hours or 24),
        )
        text_body = plain_admin_password_lockout(
            reset_link=reset_link,
            report_link=report_link,
            ip_address=ip_address,
            browser_label=browser_label,
            detected_at=clean_detected_at,
            reset_link_expire_minutes=expire_minutes,
            report_link_expire_hours=int(report_link_expire_hours or 24),
        )
        details = {
            "ip": ip_address,
            "user_agent": browser_label,
            "detected_at": clean_detected_at,
            "expire_minutes": expire_minutes,
            "report_link_expire_hours": int(report_link_expire_hours or 24),
        }
        return self._send_and_record(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            db=db,
            utilisateur_id=utilisateur_id,
            type_notification="ADMIN_PASSWORD_LOCKOUT_SECURITY_ALERT",
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            details=details,
            debug_details={**details, "reset_link": reset_link, "report_link": report_link},
            attach_background=True,
        )

    def send_admin_mfa_blocked_email(
        self,
        to_email: str,
        backup_code_link: str,
        mfa_reset_link: str,
        db: Session | None = None,
        utilisateur_id=None,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
        details: dict | None = None,
        role: str | None = None,
    ) -> bool:
        role_value = str(role or self._get_user_role(db, utilisateur_id) or "").upper()
        warning = (
            "Si vous n’êtes pas à l’origine de cette action, vérifiez immédiatement "
            "l’activité récente de votre compte."
            if role_value == "SUPER_ADMIN"
            else "Si vous n’êtes pas à l’origine de cette action, contactez immédiatement "
            "l’administrateur."
        )
        message = (
            "Plusieurs tentatives de vérification MFA échouées ont été détectées "
            "sur votre compte.\n\n"
            "Par sécurité, la vérification par application Authenticator est "
            "temporairement bloquée pendant 15 minutes.\n\n"
            "Vous pouvez continuer avec un code de secours ou réinitialiser votre MFA "
            "en scannant un nouveau QR code.\n\n"
            "Ces liens expirent dans 15 minutes.\n\n"
            f"{warning}"
        )
        html_body = render_layout(
            "Vérification MFA bloquée",
            multiline_html(message)
            + action_button("Utiliser un code de secours", backup_code_link, danger=False)
            + action_button("Réinitialiser ma MFA", mfa_reset_link, danger=True),
            danger=True,
            use_background=True,
        )
        text_body = (
            plain_security_alert(message)
            + f"\nUtiliser un code de secours : {backup_code_link}\n"
            + f"Réinitialiser ma MFA : {mfa_reset_link}\n"
        )
        return self._send_and_record(
            to_email=to_email,
            subject="Blocage temporaire de la vérification MFA",
            html_body=html_body,
            text_body=text_body,
            db=db,
            utilisateur_id=utilisateur_id,
            type_notification="ADMIN_MFA_BLOCKED",
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            details={**(details or {}), "type": "ADMIN_MFA_BLOCKED"},
            debug_details={
                "backup_code_link": backup_code_link,
                "mfa_reset_link": mfa_reset_link,
            },
            attach_background=True,
        )

    def _two_action_buttons(self, backup_code_link: str, mfa_reset_link: str) -> str:
        from app.services.mail_templates.base import action_button

        return (
            action_button("Utiliser un code de secours", backup_code_link, danger=False)
            + action_button("Réinitialiser ma MFA", mfa_reset_link, danger=True)
        )

    def send_admin_reset_password_mfa_recovery_email(
        self,
        to_email: str,
        recovery_link: str,
        db: Session | None = None,
        utilisateur_id=None,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
        details: dict | None = None,
    ) -> bool:
        message = (
            "Plusieurs codes MFA incorrects ont été saisis pendant une tentative "
            "de récupération de votre compte administrateur.\n\n"
            "Pour continuer de manière sécurisée, utilisez un code de récupération."
        )
        return self.send_security_alert_email(
            to_email=to_email,
            subject="Vérification de sécurité bloquée",
            message=message,
            action_link=recovery_link,
            db=db,
            utilisateur_id=utilisateur_id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            details={**(details or {}), "type": "ADMIN_RESET_PASSWORD_MFA_RECOVERY"},
        )

    def send_mfa_reset_success_email(
        self,
        to_email: str,
        db: Session | None = None,
        utilisateur_id=None,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
    ) -> bool:
        return self.send_security_alert_email(
            to_email=to_email,
            subject="Réinitialisation MFA réussie",
            message="Votre MFA a été réinitialisée avec succès. Une nouvelle connexion est requise.",
            db=db,
            utilisateur_id=utilisateur_id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            details={"type": "MFA_RESET_SUCCESS"},
        )

    def send_mfa_reset_failed_email(
        self,
        to_email: str,
        db: Session | None = None,
        utilisateur_id=None,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
    ) -> bool:
        return self.send_security_alert_email(
            to_email=to_email,
            subject="Réinitialisation MFA interrompue",
            message=(
                "La réinitialisation MFA a été interrompue pour des raisons de sécurité. "
                "Si vous n’êtes pas à l’origine de cette action, contactez l’administrateur système."
            ),
            db=db,
            utilisateur_id=utilisateur_id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            details={"type": "MFA_RESET_FAILED"},
        )

    def send_recovery_blocked_email(
        self,
        to_email: str,
        db: Session | None = None,
        utilisateur_id=None,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
        role: str | None = None,
    ) -> bool:
        role_value = str(role or self._get_user_role(db, utilisateur_id) or "").upper()
        if role_value == "SUPER_ADMIN":
            help_text = "Vérifiez immédiatement l’activité récente de votre compte."
            account_label = "votre compte super administrateur"
        elif role_value == "USER":
            help_text = (
                "Si vous n’avez plus accès à ces codes, contactez l’administrateur "
                "de votre département."
            )
            account_label = "votre compte"
        else:
            help_text = (
                "Si vous n’avez plus accès à ces codes, contactez le super administrateur."
            )
            account_label = "votre compte administrateur"
        return self.send_security_alert_email(
            to_email=to_email,
            subject="Alerte de sécurité - récupération temporairement bloquée",
            message=(
                "Trop de tentatives avec des codes de récupération incorrects ont été détectées.\n\n"
                f"La récupération est temporairement bloquée pour protéger {account_label}.\n\n"
                "Vérifiez vos téléchargements ou votre boîte mail : vos codes de secours vous ont été fournis "
                "lors de l’activation de votre compte.\n\n"
                f"{help_text}"
            ),
            db=db,
            utilisateur_id=utilisateur_id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            details={"type": "RECOVERY_BLOCKED", "role": role_value or None},
        )

    def send_recovery_supervisor_action_email(
        self,
        to_email: str,
        target_email: str,
        target_role: str,
        department: str,
        disable_link: str,
        regenerate_link: str,
        db: Session | None = None,
        utilisateur_id=None,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
        details: dict | None = None,
    ) -> bool:
        role_value = str(target_role or "").upper()
        is_admin_target = role_value == "ADMIN"
        subject = (
            "Action requise - codes de secours invalides administrateur"
            if is_admin_target
            else "Action requise - codes de secours invalides"
        )
        target_label = "L’administrateur" if is_admin_target else "L’utilisateur"
        disable_label = (
            "Désactiver ce compte administrateur"
            if is_admin_target
            else "Désactiver ce compte"
        )
        message = (
            f"{target_label} suivant a saisi plusieurs codes de secours invalides :\n\n"
            f"Compte : {target_email}\n"
            f"Département : {department}\n\n"
            "Veuillez choisir l’action à appliquer."
        )
        html_body = render_layout(
            subject,
            multiline_html(message)
            + action_button(disable_label, disable_link, danger=True)
            + action_button("Régénérer et envoyer les codes", regenerate_link, danger=False)
            + multiline_html("Ces liens sont valables pendant 15 minutes et utilisables une seule fois."),
            danger=True,
            use_background=True,
        )
        text_body = (
            plain_security_alert(message)
            + f"\n{disable_label} : {disable_link}\n"
            + f"Régénérer et envoyer les codes : {regenerate_link}\n"
            + "\nCes liens sont valables pendant 15 minutes et utilisables une seule fois.\n"
        )
        return self._send_and_record(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            db=db,
            utilisateur_id=utilisateur_id,
            type_notification="RECOVERY_CODE_SUPERVISOR_ACTION",
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            details=details or {},
            debug_details={**(details or {}), "disable_link": disable_link, "regenerate_link": regenerate_link},
            attach_background=True,
        )

    def send_account_reactivation_request_email(
        self,
        to_email: str,
        target_email: str,
        target_role: str,
        department: str,
        reactivate_link: str,
        ignore_link: str,
        db: Session | None = None,
        utilisateur_id=None,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
        details: dict | None = None,
    ) -> bool:
        role_value = str(target_role or "").upper()
        is_admin_target = role_value == "ADMIN"
        subject = (
            "Demande de réactivation de compte administrateur"
            if is_admin_target
            else "Demande de réactivation de compte utilisateur"
        )
        target_label = "L’administrateur" if is_admin_target else "L’utilisateur"
        reactivate_label = (
            "Réactiver le compte administrateur"
            if is_admin_target
            else "Réactiver le compte"
        )
        message = (
            f"{target_label} suivant demande la réactivation de son compte :\n\n"
            f"Compte : {target_email}\n"
            f"Département : {department}\n\n"
            "Veuillez choisir l’action à appliquer."
        )
        html_body = render_layout(
            subject,
            multiline_html(message)
            + action_button(reactivate_label, reactivate_link, danger=False)
            + action_button("Ignorer la demande", ignore_link, danger=True)
            + multiline_html("Ces liens sont valables pendant 24 heures et utilisables une seule fois."),
            danger=False,
            use_background=True,
        )
        text_body = (
            plain_security_alert(message)
            + f"\n{reactivate_label} : {reactivate_link}\n"
            + f"Ignorer la demande : {ignore_link}\n"
            + "\nCes liens sont valables pendant 24 heures et utilisables une seule fois.\n"
        )
        return self._send_and_record(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            db=db,
            utilisateur_id=utilisateur_id,
            type_notification="ACCOUNT_REACTIVATION_REQUEST",
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            details=details or {},
            debug_details={**(details or {}), "reactivate_link": reactivate_link, "ignore_link": ignore_link},
            attach_background=True,
        )

    def send_secure_recovery_required_email(
        self,
        to_email: str,
        secure_link: str,
        db: Session | None = None,
        utilisateur_id=None,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
    ) -> bool:
        return self.send_security_alert_email(
            to_email=to_email,
            subject="Connexion sécurisée requise",
            message=(
                "Plusieurs codes de secours invalides ont été saisis.\n\n"
                "Par sécurité, vous ne pouvez plus vous connecter directement depuis la plateforme pendant cette période.\n\n"
                "Veuillez utiliser le lien sécurisé ci-dessous pour reprendre votre connexion.\n\n"
                "Ce lien expire dans 24 heures. Toute tentative de connexion hors de ce lien sera refusée pendant cette période."
            ),
            action_link=secure_link,
            db=db,
            utilisateur_id=utilisateur_id,
            adresse_ip=adresse_ip,
            user_agent=user_agent,
            details={"type": "SUPER_ADMIN_SECURE_RECOVERY_24H"},
        )

    def _send_and_record(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str,
        db: Session | None,
        utilisateur_id,
        type_notification: str,
        adresse_ip: str | None = None,
        user_agent: str | None = None,
        details: dict | None = None,
        debug_details: dict | None = None,
        attach_background: bool = False,
    ) -> bool:
        try:
            sent = self._send_email(
                to_email=to_email,
                subject=subject,
                html_body=html_body,
                text_body=text_body,
                attach_background=attach_background,
            )

            self._record_notification(
                db=db,
                utilisateur_id=utilisateur_id,
                type_notification=type_notification,
                email_destinataire=to_email,
                sujet=subject,
                statut="ENVOYE" if sent else "ECHEC",
                adresse_ip=adresse_ip,
                user_agent=user_agent,
                details=debug_details if settings.MAIL_DEBUG_MODE and debug_details else (details or {}),
            )
            return sent

        except Exception as exc:
            try:
                self._record_notification(
                    db=db,
                    utilisateur_id=utilisateur_id,
                    type_notification=type_notification,
                    email_destinataire=to_email,
                    sujet=subject,
                    statut="ECHEC",
                    erreur_envoi=str(exc),
                    adresse_ip=adresse_ip,
                    user_agent=user_agent,
                    details=details or {},
                )
            except Exception:
                pass
            return False
