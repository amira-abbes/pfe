import html
import re

from app.services.mail_templates.styles import (
    COLORS,
    button_style,
    heading_style,
    note_style,
    paragraph_style,
)


ELLIPSIS_BLOCK_RE = re.compile(
    r"<(p|div|span)\b[^>]*>\s*(?:\.{3}|\u2026|&hellip;)\s*</\1>",
    flags=re.IGNORECASE,
)
ELLIPSIS_LINE_RE = re.compile(r"(?m)^\s*(?:\.{3}|\u2026|&hellip;)\s*$")

MOJIBAKE_FIXES = {
    "\u00c3\u00a9": "\u00e9",
    "\u00c3\u00a8": "\u00e8",
    "\u00c3\u00aa": "\u00ea",
    "\u00c3\u00ab": "\u00eb",
    "\u00c3\u00a0": "\u00e0",
    "\u00c3\u00a2": "\u00e2",
    "\u00c3\u00b4": "\u00f4",
    "\u00c3\u00ae": "\u00ee",
    "\u00c3\u00af": "\u00ef",
    "\u00c3\u00bb": "\u00fb",
    "\u00c3\u00b9": "\u00f9",
    "\u00c3\u00a7": "\u00e7",
    "\u00c3\u2030": "\u00c9",
    "\u00e2\u20ac\u2122": "\u2019",
    "\u00e2\u20ac\u0153": "\u201c",
    "\u00e2\u20ac\u009d": "\u201d",
    "\u00e2\u20ac\u201d": "\u2014",
    "\u00e2\u20ac\u201c": "\u2013",
    "\u00e2\u20ac\u00a6": "",
}


def repair_text(value: str) -> str:
    repaired = str(value or "")
    for bad, good in MOJIBAKE_FIXES.items():
        repaired = repaired.replace(bad, good)
    return repaired


def clean_email_content(content: str) -> str:
    cleaned = repair_text(str(content or ""))
    cleaned = ELLIPSIS_BLOCK_RE.sub("", cleaned)
    cleaned = ELLIPSIS_LINE_RE.sub("", cleaned)
    return cleaned.replace("...", "").replace("\u2026", "").strip()


def safe(value) -> str:
    return html.escape(repair_text(str(value)), quote=True)


def multiline_html(text: str) -> str:
    paragraphs = [part.strip() for part in repair_text(text).split("\n\n") if part.strip()]
    if not paragraphs:
        return ""
    return "\n".join(
        f'<p style="{paragraph_style()}">{safe(part).replace(chr(10), "<br>")}</p>'
        for part in paragraphs
    )


def action_button(label: str, link: str, danger: bool = False, note: str | None = None) -> str:
    note_html = f'<div style="{note_style()}">{safe(note)}</div>' if note else ""
    return f"""
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:22px 0;">
        <tr>
          <td align="center">
            <a href="{safe(link)}" style="{button_style(danger=danger)}">{safe(label)}</a>
            {note_html}
          </td>
        </tr>
      </table>
    """


def details_box(items: list[tuple[str, str]]) -> str:
    rows = "".join(
        f"<strong>{safe(label)} :</strong> {safe(value)}<br>"
        for label, value in items
    )
    return f"""
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
        style="margin:16px 0 20px;background:#fff7f7;border:1px solid #fecdca;border-radius:8px;">
        <tr>
          <td style="padding:15px;color:{COLORS['red_dark']};font-size:14px;line-height:1.75;">
            {rows}
          </td>
        </tr>
      </table>
    """


def code_grid(codes: list[str]) -> str:
    rows = []
    for index in range(0, len(codes), 2):
        left = safe(codes[index])
        right = safe(codes[index + 1]) if index + 1 < len(codes) else ""
        cell_style = (
            "padding:12px 10px;border:1px solid #d0d5dd;background:#f9fafb;"
            f"color:{COLORS['blue_dark']};font-family:Consolas,monospace;"
            "font-size:16px;font-weight:800;text-align:center;letter-spacing:1px;"
        )
        rows.append(
            f"""
            <tr>
              <td width="50%" style="{cell_style}">{left}</td>
              <td width="50%" style="{cell_style}">{right}</td>
            </tr>
            """
        )
    return f"""
      <table role="presentation" width="100%" cellpadding="6" cellspacing="0" style="margin:16px 0;">
        {''.join(rows)}
      </table>
    """


def render_layout(
    title: str,
    body_html: str,
    danger: bool = False,
    use_background: bool = False,
) -> str:
    page_background = COLORS["soft_red"] if danger else COLORS["soft_blue"]
    accent_color = COLORS["red"] if danger else COLORS["blue"]

    return clean_email_content(f"""
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:{page_background};font-family:Arial,Helvetica,sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
      style="width:100%;min-width:100%;padding:28px 12px;background-color:{page_background};">
      <tr>
        <td align="center">
          <table role="presentation" width="600" cellpadding="0" cellspacing="0"
            style="width:100%;max-width:600px;background:{COLORS['panel']};border-radius:8px;overflow:hidden;border:1px solid #dbe3ef;">
            <tr>
              <td style="height:8px;line-height:8px;font-size:0;background:{accent_color};">&nbsp;</td>
            </tr>
            <tr>
              <td style="padding:30px 30px 28px;">
                <img src="cid:tt_logo" alt="Tunisie Telecom"
                  style="display:block;width:156px;max-width:62%;height:auto;margin:0 auto 22px auto;border:0;" />
                <h1 style="{heading_style(danger=danger)}">{safe(title)}</h1>
                {body_html}
                <p style="margin:22px 0 0;color:{COLORS['text']};font-size:14px;line-height:1.6;text-align:center;">
                  Cordialement,<br>
                  <strong>Tunisie Telecom Platform</strong>
                </p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
""")


_email_layout = render_layout
_content_card = multiline_html
_button_html = action_button
_alert_box = details_box
_info_box = details_box
_codes_grid_html = code_grid
_sanitize_email_html = clean_email_content
_sanitize_email_text = clean_email_content
