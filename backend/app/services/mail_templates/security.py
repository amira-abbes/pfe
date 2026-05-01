from app.services.mail_templates.base import (
    action_button,
    details_box,
    multiline_html,
    render_layout,
)
from app.services.mail_templates.styles import note_style, paragraph_style


MFA_BLOCKED_MESSAGE = (
    "Plusieurs codes de vérification incorrects ont été saisis lors d’une "
    "tentative de récupération de votre compte.\n\n"
    "Par sécurité, la vérification par application Authenticator a été temporairement bloquée.\n\n"
    "Vous pouvez continuer la récupération en utilisant un code de secours.\n\n"
    "Si vous n’êtes pas à l’origine de cette action, contactez immédiatement l’administrateur."
)


def security_alert_email(
    title: str,
    message: str,
    action_link: str | None = None,
    action_label: str = "Ouvrir le lien sécurisé",
) -> str:
    body = multiline_html(message)
    if action_link:
        body += action_button(action_label, action_link, danger=True)
    return render_layout(title, body, danger=True, use_background=True)


def mfa_blocked_email() -> str:
    return security_alert_email(
        title="Alerte de sécurité",
        message=MFA_BLOCKED_MESSAGE,
    )


def lockout_security_email(
    reset_link: str,
    report_link: str,
    ip_address: str,
    browser_label: str,
    detected_at: str,
    reset_link_expire_minutes: int,
    report_link_expire_hours: int,
) -> str:
    intro = multiline_html(
        "Bonjour,\n\n"
        "Plusieurs tentatives de connexion échouées ont été détectées sur votre compte."
    )
    details = details_box(
        [
            ("Adresse IP", ip_address),
            ("Navigateur / appareil", browser_label),
            ("Date et heure", detected_at),
        ]
    )
    body = f"""
      {intro}
      {details}
      <p style="{paragraph_style()}">Par sécurité, votre compte a été temporairement bloqué et vos sessions actives ont été révoquées.</p>
      {action_button(
        "C’était moi — changer mon mot de passe",
        reset_link,
        danger=False,
        note=f"Lien valable {reset_link_expire_minutes} minutes.",
      )}
      {action_button(
        "Ce n’était pas moi — signaler l’activité",
        report_link,
        danger=True,
        note=f"Lien valable {report_link_expire_hours} heures.",
      )}
      <p style="{note_style()}">Le lien de changement de mot de passe expire dans {reset_link_expire_minutes} minutes. Le lien de signalement reste valable pendant {report_link_expire_hours} heures.</p>
    """
    return render_layout("Alerte de sécurité", body, danger=True, use_background=True)


def admin_password_lockout_email(
    reset_link: str,
    report_link: str,
    ip_address: str,
    browser_label: str,
    detected_at: str,
    reset_link_expire_minutes: int,
    report_link_expire_hours: int,
) -> str:
    intro = multiline_html(
        "Bonjour,\n\n"
        "Plusieurs tentatives de connexion incorrectes ont été détectées sur votre compte administrateur.\n\n"
        "Par sécurité, l’accès a été temporairement bloqué pendant 15 minutes.\n\n"
        "Si c’était vous, vous pouvez réinitialiser votre mot de passe depuis le lien sécurisé ci-dessous.\n\n"
        "Si ce n’était pas vous, signalez immédiatement cette activité."
    )
    details = details_box(
        [
            ("Adresse IP", ip_address),
            ("Navigateur / appareil", browser_label),
            ("Date et heure", detected_at),
        ]
    )
    body = f"""
      {intro}
      {details}
      {action_button("C’était moi — changer mon mot de passe", reset_link, danger=False, note=f"Lien valable {reset_link_expire_minutes} minutes.")}
      {action_button("Ce n’était pas moi — signaler l’activité", report_link, danger=True, note=f"Lien valable {report_link_expire_hours} heures.")}
      <p style="{note_style()}">Le lien de changement de mot de passe expire dans {reset_link_expire_minutes} minutes. Le lien de signalement reste valable pendant {report_link_expire_hours} heures.</p>
    """
    return render_layout(
        "Compte administrateur temporairement bloqué",
        body,
        danger=True,
        use_background=True,
    )


def plain_security_alert(message: str, action_link: str | None = None) -> str:
    button_text = f"\nLien sécurisé : {action_link}\n" if action_link else ""
    return f"""Bonjour,

{message}
{button_text}
Cordialement,
Tunisie Telecom Platform
"""


def plain_admin_password_lockout(
    reset_link: str,
    report_link: str,
    ip_address: str,
    browser_label: str,
    detected_at: str,
    reset_link_expire_minutes: int,
    report_link_expire_hours: int,
) -> str:
    return f"""Bonjour,

Plusieurs tentatives de connexion incorrectes ont été détectées sur votre compte administrateur.

Par sécurité, l’accès a été temporairement bloqué pendant 15 minutes.

Si c’était vous, vous pouvez réinitialiser votre mot de passe depuis le lien sécurisé ci-dessous.

Si ce n’était pas vous, signalez immédiatement cette activité.

Adresse IP : {ip_address}
Navigateur / appareil : {browser_label}
Date et heure : {detected_at}

C’était moi — changer mon mot de passe :
{reset_link}
Lien valable {reset_link_expire_minutes} minutes.

Ce n’était pas moi — signaler l’activité :
{report_link}
Lien valable {report_link_expire_hours} heures.

Le lien de changement de mot de passe expire dans {reset_link_expire_minutes} minutes.
Le lien de signalement reste valable pendant {report_link_expire_hours} heures.

Cordialement,
Tunisie Telecom Platform
"""


def plain_lockout_security(
    reset_link: str,
    report_link: str,
    ip_address: str,
    browser_label: str,
    detected_at: str,
    reset_link_expire_minutes: int,
    report_link_expire_hours: int,
) -> str:
    return f"""Bonjour,

Plusieurs tentatives de connexion échouées ont été détectées sur votre compte.

Adresse IP : {ip_address}
Navigateur / appareil : {browser_label}
Date et heure : {detected_at}

Par sécurité, votre compte a été temporairement bloqué et vos sessions actives ont été révoquées.

C’était moi — changer mon mot de passe :
{reset_link}
Lien valable {reset_link_expire_minutes} minutes.

Ce n’était pas moi — signaler l’activité :
{report_link}
Lien valable {report_link_expire_hours} heures.

Le lien de changement de mot de passe expire dans {reset_link_expire_minutes} minutes.
Le lien de signalement reste valable pendant {report_link_expire_hours} heures.

Cordialement,
Tunisie Telecom Platform
"""
