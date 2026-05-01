from app.services.mail_templates.base import (
    action_button,
    code_grid,
    multiline_html,
    render_layout,
    safe,
)
from app.services.mail_templates.styles import note_style


def activation_email(activation_link: str, expire_minutes: int) -> str:
    intro = multiline_html(
        "Bonjour,\n\n"
        "Votre compte sur la plateforme interne Tunisie Telecom a été créé. "
        "Cliquez sur le bouton ci-dessous pour activer votre compte et définir votre mot de passe."
    )
    button = action_button("Activer mon compte", activation_link)
    note = f'<p style="{note_style()}">Ce lien est valable pendant {expire_minutes} minutes.</p>'
    return render_layout("Activation de votre compte", f"{intro}{button}{note}")


def password_reset_email(reset_link: str, expire_minutes: int, from_lockout: bool = False) -> str:
    title = "Récupération de votre accès" if from_lockout else "Réinitialisation du mot de passe"
    intro = multiline_html(
        "Bonjour,\n\n"
        "Une demande de réinitialisation de mot de passe a été initiée pour votre compte.\n\n"
        "Si vous êtes à l’origine de cette demande, cliquez sur le bouton ci-dessous."
    )
    button = action_button("Réinitialiser mon mot de passe", reset_link)
    note_text = (
        f"Ce lien expire dans {expire_minutes} minutes. "
        "Si vous n’êtes pas à l’origine de cette demande, ignorez cet email ou contactez l’administrateur."
    )
    note = f'<p style="{note_style()}">{safe(note_text)}</p>'
    return render_layout(title, f"{intro}{button}{note}", danger=from_lockout)


def _recovery_warning(role: str | None) -> str:
    if str(role or "").upper() == "SUPER_ADMIN":
        return (
            "Si vous n’êtes pas à l’origine de cette action, changez immédiatement "
            "votre mot de passe et vérifiez l’activité récente de votre compte."
        )
    return "Si vous n’êtes pas à l’origine de cette action, contactez immédiatement l’administrateur."


def recovery_codes_email(recovery_codes: list[str], role: str | None = None) -> str:
    intro = multiline_html(
        "Bonjour,\n\n"
        "Vos codes de secours ont été régénérés avec succès.\n\n"
        "Les anciens codes de secours ont été invalidés. Seuls les nouveaux codes peuvent désormais être utilisés.\n\n"
        "Conservez ces codes dans un endroit sûr. Ils peuvent vous permettre de récupérer l’accès à votre compte si vous ne pouvez plus utiliser votre application Authenticator.\n\n"
        f"{_recovery_warning(role)}"
    )
    codes_html = code_grid(recovery_codes) if recovery_codes else ""
    return render_layout("Codes de secours régénérés", f"{intro}{codes_html}")


def plain_activation(activation_link: str, expire_minutes: int) -> str:
    return f"""Bonjour,

Votre compte sur la plateforme interne Tunisie Telecom a été créé.

Lien d’activation :
{activation_link}

Ce lien est valable pendant {expire_minutes} minutes.

Cordialement,
Tunisie Telecom Platform
"""


def plain_password_reset(reset_link: str, expire_minutes: int) -> str:
    return f"""Bonjour,

Une demande de réinitialisation de mot de passe a été initiée pour votre compte.

Si vous êtes à l’origine de cette demande, utilisez le lien ci-dessous.

Lien de réinitialisation :
{reset_link}

Ce lien expire dans {expire_minutes} minutes.

Si vous n’êtes pas à l’origine de cette demande, ignorez cet email ou contactez l’administrateur.

Cordialement,
Tunisie Telecom Platform
"""


def plain_recovery_codes(recovery_codes: list[str], role: str | None = None) -> str:
    codes_text = "\n".join(f"- {safe(code)}" for code in recovery_codes)
    return f"""Bonjour,

Vos codes de secours ont été régénérés avec succès.

Les anciens codes de secours ont été invalidés. Seuls les nouveaux codes peuvent désormais être utilisés.

Conservez ces codes dans un endroit sûr. Ils peuvent vous permettre de récupérer l’accès à votre compte si vous ne pouvez plus utiliser votre application Authenticator.

{_recovery_warning(role)}

Codes :
{codes_text}

Cordialement,
Tunisie Telecom Platform
"""
