COLORS = {
    "blue": "#0046d8",
    "blue_dark": "#071d5b",
    "red": "#d92d20",
    "red_dark": "#912018",
    "text": "#14245a",
    "muted": "#667085",
    "line": "#d0d5dd",
    "panel": "#ffffff",
    "soft_blue": "#f3f6fb",
    "soft_red": "#fff6f5",
    "soft_gray": "#f9fafb",
}


def button_style(danger: bool = False) -> str:
    color = COLORS["red"] if danger else COLORS["blue"]
    return (
        "display:inline-block;"
        "width:82%;"
        "max-width:360px;"
        "padding:15px 24px;"
        "border-radius:14px;"
        f"background:{color};"
        "color:#ffffff;"
        "text-decoration:none;"
        "font-weight:800;"
        "font-size:15px;"
        "line-height:1.3;"
    )


def paragraph_style() -> str:
    return f"margin:0 0 18px;color:{COLORS['text']};font-size:15px;line-height:1.7;"


def note_style() -> str:
    return f"margin:8px 0 0;color:{COLORS['muted']};font-size:13px;line-height:1.5;"


def heading_style(danger: bool = False) -> str:
    color = COLORS["red_dark"] if danger else COLORS["blue_dark"]
    return (
        "margin:0 0 22px;"
        f"color:{color};"
        "font-size:25px;"
        "line-height:1.25;"
        "text-align:center;"
        "font-weight:800;"
    )
