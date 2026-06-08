from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from app.core.elt_config import TT_LOGO_FILE
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    HRFlowable,
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


BLACK = colors.HexColor("#0F172A")
GRAY_900 = colors.HexColor("#27334A")
GRAY_600 = colors.HexColor("#64748B")
GRAY_300 = colors.HexColor("#E2E8F0")
GRAY_100 = colors.HexColor("#F8FAFC")
WHITE = colors.HexColor("#FFFFFF")
TT_BLUE = colors.HexColor("#1E4ED8")
TT_VIOLET = colors.HexColor("#7C3AED")
TT_TURQUOISE = colors.HexColor("#22C7D6")
TT_LIGHT_BLUE = colors.HexColor("#EAF3FF")
TT_GREEN = colors.HexColor("#22A06B")
TT_YELLOW = colors.HexColor("#FACC15")
TT_ORANGE = colors.HexColor("#F97316")
TT_RED = colors.HexColor("#E11D48")
TT_PALETTE = (TT_BLUE, TT_TURQUOISE, TT_GREEN, TT_YELLOW, TT_ORANGE, TT_RED, TT_VIOLET)
RISK_HIGH = TT_RED
RISK_MEDIUM = TT_ORANGE
RISK_LOW = TT_GREEN


def style(name, **kw):
    base = dict(
        fontName="Helvetica",
        fontSize=9,
        leading=14,
        textColor=BLACK,
        spaceAfter=0,
    )
    base.update(kw)
    return ParagraphStyle(name, **base)


S_TITLE = style("title", fontName="Helvetica-Bold", fontSize=23, leading=28, textColor=TT_BLUE)
S_MAIN_TITLE = style("main-title", fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=TT_BLUE, alignment=TA_CENTER)
S_MAIN_SUB = style("main-sub", fontSize=9, textColor=GRAY_600, leading=13, alignment=TA_CENTER)
S_SUB = style("sub", fontSize=9, textColor=GRAY_600, leading=13)
S_LABEL = style("label", fontName="Helvetica-Bold", fontSize=7, textColor=GRAY_600)
S_BODY = style("body", fontSize=8.5, textColor=GRAY_600, leading=13)
S_SECTION = style("section", fontName="Helvetica-Bold", fontSize=11, textColor=TT_BLUE)
S_CENTER = style("center", fontSize=7, textColor=GRAY_600, alignment=TA_CENTER)
S_CARD_TITLE = style("card-title", fontName="Helvetica-Bold", fontSize=8.5, textColor=BLACK, leading=11)
SP = lambda n: Spacer(1, n * mm)


def _canvas_text(value: Any) -> str:
    return (
        str(value if value not in (None, "") else "Non disponible")
        .replace("\u2014", "-")
        .replace("\u2013", "-")
        .replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("\u00a0", " ")
    )


def _wrap(canvas, value: Any, font: str, size: float, max_width: float, max_lines: int | None = None) -> list[str]:
    words = _canvas_text(value).split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        if current and canvas.stringWidth(test, font, size) > max_width:
            lines.append(current)
            current = word
            if max_lines and len(lines) >= max_lines:
                break
        else:
            current = test
    if current and (not max_lines or len(lines) < max_lines):
        lines.append(current)
    if max_lines and len(lines) == max_lines and len(" ".join(lines).split()) < len(words):
        line = lines[-1]
        while line and canvas.stringWidth(f"{line}...", font, size) > max_width:
            line = line[:-1]
        lines[-1] = f"{line.rstrip()}..."
    return lines or [""]


class MiniKPI(Flowable):
    def __init__(self, value, label, sub, dot_color, width, height):
        super().__init__()
        self.value = value
        self.label = label
        self.sub = sub
        self.dot_color = dot_color
        self.width = width
        self.height = height

    def wrap(self, avail_width, avail_height):
        return self.width, self.height

    def draw(self):
        canvas = self.canv
        canvas.saveState()
        canvas.setFillColor(WHITE)
        canvas.setStrokeColor(GRAY_300)
        canvas.setLineWidth(0.45)
        canvas.roundRect(0, 0, self.width - 1.2 * mm, self.height, 4, fill=1, stroke=1)
        canvas.setFillColor(self.dot_color)
        canvas.roundRect(0, self.height - 1.25 * mm, self.width - 1.2 * mm, 1.25 * mm, 2, fill=1, stroke=0)
        canvas.setFillColor(self.dot_color)
        canvas.setFont("Helvetica-Bold", 17)
        canvas.drawString(2.5 * mm, self.height - 9 * mm, _canvas_text(self.value))
        canvas.setFillColor(GRAY_600)
        canvas.setFont("Helvetica-Bold", 7)
        canvas.drawString(2.5 * mm, self.height - 13.2 * mm, _canvas_text(self.label))
        canvas.setFillColor(GRAY_300)
        canvas.setFont("Helvetica", 6.5)
        for index, line in enumerate(_wrap(canvas, self.sub, "Helvetica", 6.5, self.width - 5 * mm, 2)):
            canvas.drawString(2.5 * mm, self.height - (17 + index * 3) * mm, line)
        canvas.restoreState()


class MulticolorLine(Flowable):
    def __init__(self, width, height=0.8):
        super().__init__()
        self.width = width
        self.height = height

    def wrap(self, avail_width, avail_height):
        return self.width, self.height

    def draw(self):
        _draw_multicolor_line(self.canv, 0, 0, self.width, self.height)


class DotBar(Flowable):
    def __init__(self, items, width):
        super().__init__()
        self.items = items
        self.width = width
        self.height = len(items) * 8 * mm

    def wrap(self, avail_width, avail_height):
        return self.width, self.height

    def draw(self):
        canvas = self.canv
        canvas.saveState()
        bar_start = min(38 * mm, self.width * 0.43)
        bar_end = self.width - 24 * mm
        bar_width = max(1, bar_end - bar_start)
        for index, (label, value, pct, color) in enumerate(self.items):
            y = self.height - (index * 8 + 5) * mm
            canvas.setFillColor(color)
            canvas.circle(2 * mm, y + 1.2 * mm, 1.8 * mm, fill=1, stroke=0)
            canvas.setFillColor(GRAY_900)
            canvas.setFont("Helvetica", 7)
            canvas.drawString(6 * mm, y, _canvas_text(label))
            canvas.setFillColor(GRAY_100)
            canvas.roundRect(bar_start, y, bar_width, 3.2 * mm, 1.6 * mm, fill=1, stroke=0)
            canvas.setFillColor(color)
            canvas.roundRect(bar_start, y, max(1, bar_width * max(0, min(float(pct), 1))), 3.2 * mm, 1.6 * mm, fill=1, stroke=0)
            canvas.setFillColor(GRAY_900)
            canvas.setFont("Helvetica-Bold", 6.4)
            canvas.drawRightString(self.width, y, f"{_canvas_text(value)} ({max(0, min(float(pct), 1)) * 100:.0f} %)")
        canvas.restoreState()


class PriorityRow(Flowable):
    def __init__(self, num, title, target, body, color, width):
        super().__init__()
        self.num = num
        self.title = title
        self.target = target
        self.body = body
        self.color = color
        self.width = width
        self.height = 22 * mm

    def wrap(self, avail_width, avail_height):
        return self.width, self.height

    def draw(self):
        canvas = self.canv
        canvas.saveState()
        tint = colors.Color(self.color.red, self.color.green, self.color.blue, alpha=0.07)
        canvas.setFillColor(tint)
        canvas.roundRect(0, 0, self.width, self.height, 4, fill=1, stroke=0)
        canvas.setFillColor(self.color)
        canvas.roundRect(0, 0, 2 * mm, self.height, 2, fill=1, stroke=0)
        canvas.circle(7 * mm, self.height - 8 * mm, 4 * mm, fill=1, stroke=0)
        canvas.setFillColor(WHITE)
        canvas.setFont("Helvetica-Bold", 15)
        canvas.drawCentredString(7 * mm, self.height - 9.8 * mm, _canvas_text(self.num))
        canvas.setFillColor(BLACK)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(14 * mm, self.height - 6.5 * mm, _canvas_text(self.title))
        canvas.setFillColor(GRAY_600)
        canvas.setFont("Helvetica-Bold", 7)
        for index, line in enumerate(_wrap(canvas, self.target, "Helvetica-Bold", 7, self.width - 17 * mm, 2)):
            canvas.drawString(14 * mm, self.height - (10 + index * 3.2) * mm, line)
        canvas.setFont("Helvetica", 7)
        for index, line in enumerate(_wrap(canvas, self.body, "Helvetica", 7, self.width - 17 * mm, 2)):
            canvas.drawString(14 * mm, self.height - (16.5 + index * 3.2) * mm, line)
        canvas.restoreState()


class RecBlock(Flowable):
    def __init__(self, num, title, why, example, impact, width, accent=TT_BLUE):
        super().__init__()
        self.num = num
        self.title = title
        self.why = why
        self.example = example
        self.impact = impact
        self.width = width
        self.height = 44 * mm
        self.accent = accent

    def wrap(self, avail_width, avail_height):
        return self.width, self.height

    def draw(self):
        canvas = self.canv
        canvas.saveState()
        canvas.setFillColor(colors.HexColor("#F8FBFF"))
        canvas.roundRect(0, 0, self.width, self.height, 3, fill=1, stroke=0)
        canvas.setStrokeColor(GRAY_300)
        canvas.setLineWidth(0.4)
        canvas.roundRect(0, 0, self.width, self.height, 3, fill=0, stroke=1)
        canvas.setFillColor(self.accent)
        canvas.rect(0, self.height - mm, self.width, mm, fill=1, stroke=0)
        canvas.setFillColor(self.accent)
        canvas.circle(6 * mm, self.height - 7.5 * mm, 3.5 * mm, fill=1, stroke=0)
        canvas.setFillColor(WHITE)
        canvas.setFont("Helvetica-Bold", 7)
        canvas.drawCentredString(6 * mm, self.height - 9 * mm, _canvas_text(self.num))
        canvas.setFillColor(BLACK)
        canvas.setFont("Helvetica-Bold", 8)
        title_lines = _wrap(canvas, self.title, "Helvetica-Bold", 8, self.width - 15 * mm, 2)
        for index, line in enumerate(title_lines):
            canvas.drawString(11 * mm, self.height - (7.3 + index * 3.2) * mm, line)
        separator_y = self.height - 14 * mm
        canvas.setStrokeColor(GRAY_300)
        canvas.setLineWidth(0.5)
        canvas.line(4 * mm, separator_y, self.width - 4 * mm, separator_y)
        fields = [("POURQUOI", self.why), ("EXEMPLE", self.example), ("IMPACT", self.impact)]
        y = separator_y - 5 * mm
        for label, value in fields:
            canvas.setFillColor(GRAY_600)
            canvas.setFont("Helvetica-Bold", 6.5)
            canvas.drawString(4 * mm, y, label)
            canvas.setFillColor(GRAY_900)
            canvas.setFont("Helvetica", 7)
            lines = _wrap(canvas, value, "Helvetica", 7, self.width - 8 * mm, 2)
            for index, line in enumerate(lines):
                canvas.drawString(4 * mm, y - (3.2 + index * 3) * mm, line)
            y -= 10 * mm
        canvas.restoreState()


def _paragraph(value: Any, paragraph_style: ParagraphStyle) -> Paragraph:
    safe = (
        str(value if value not in (None, "") else "Non disponible")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return Paragraph(safe, paragraph_style)


def _section_heading(value: str, width: float) -> Table:
    heading = Table([[_paragraph(value, S_SECTION)]], colWidths=[width])
    heading.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, GRAY_300),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return heading


def _chart_card(title: str, items: list[tuple[Any, Any, Any, Any]], width: float) -> Table:
    inner_width = width - 8 * mm
    card = Table(
        [[_paragraph(title, S_CARD_TITLE)], [DotBar(items, inner_width)]],
        colWidths=[width],
    )
    card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), WHITE),
        ("BOX", (0, 0), (-1, -1), 0.55, GRAY_300),
        ("LINEBELOW", (0, 0), (-1, 0), 0.4, GRAY_300),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 3 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm),
    ]))
    return card


def _summary_card(value: Any, width: float) -> Table:
    summary_style = style("summary", fontSize=8, leading=11, textColor=GRAY_900)
    card = Table([[_paragraph(value, summary_style)]], colWidths=[width])
    card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FBFF")),
        ("BOX", (0, 0), (-1, -1), 0.55, GRAY_300),
        ("LINEBEFORE", (0, 0), (0, -1), 2.2 * mm, TT_TURQUOISE),
        ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 3 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm),
    ]))
    return card


def _draw_multicolor_line(canvas, x: float, y: float, width: float, height: float = 0.8):
    segment_width = width / len(TT_PALETTE)
    for index, color in enumerate(TT_PALETTE):
        canvas.setFillColor(color)
        canvas.rect(x + index * segment_width, y, segment_width + 0.2, height, fill=1, stroke=0)


def _decorate_page(canvas, document):
    page_width, page_height = A4
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#DDE9F7"))
    canvas.setLineWidth(0.55)
    canvas.roundRect(8 * mm, 8 * mm, page_width - 16 * mm, page_height - 16 * mm, 7, fill=0, stroke=1)
    _draw_multicolor_line(canvas, 20 * mm, page_height - 11 * mm, page_width - 40 * mm, 0.7)
    canvas.setStrokeColor(GRAY_300)
    canvas.setLineWidth(0.45)
    canvas.line(20 * mm, 12 * mm, page_width - 20 * mm, 12 * mm)
    canvas.setFillColor(GRAY_600)
    _draw_multicolor_line(canvas, 20 * mm, 13.5 * mm, page_width - 40 * mm, 0.65)
    canvas.setFont("Helvetica-Bold", 6.8)
    canvas.drawString(20 * mm, 8.5 * mm, "Tunisie Telecom")
    canvas.setFont("Helvetica", 6.5)
    canvas.drawCentredString(page_width / 2, 8.5 * mm, "La vie est emotions - Rapport Bad Debts")
    canvas.drawRightString(page_width - 20 * mm, 8.5 * mm, f"Page {canvas.getPageNumber()} / 2")
    canvas.restoreState()


def _number(value: Any) -> str:
    try:
        return f"{int(value or 0):,}".replace(",", " ")
    except (TypeError, ValueError):
        return str(value or "Non disponible")


def _score(value: Any) -> str:
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return "Non disponible"


def _pct(value: Any, total: int) -> float:
    try:
        return float(value or 0) / max(total, 1)
    except (TypeError, ValueError):
        return 0


def normalize_bad_debts_report_data(payload: dict[str, Any]) -> dict[str, Any]:
    if "risk_distribution" in payload and "total_scored" in (payload.get("kpis") or {}):
        normalized = dict(payload)
        normalized["generated_at"] = payload.get("generated_at") or datetime.now().astimezone().isoformat()
        normalized["scope"] = payload.get("scope") or ("filtered" if payload.get("filters") else "global")
        normalized["scope_display"] = payload.get("scope_display") or ("Clients filtres" if normalized["scope"] == "filtered" else "Tous les clients")
        normalized["filters_display"] = payload.get("filters_display") or ("Aucun filtre actif" if not payload.get("filters") else ", ".join(f"{key} : {value}" for key, value in payload["filters"].items()))
        normalized["title"] = payload.get("title") or "Non disponible"
        normalized["subtitle"] = payload.get("subtitle") or normalized["scope_display"]
        normalized["executive_summary"] = payload.get("executive_summary") or "Non disponible"
        normalized["confidentiality"] = payload.get("confidentiality") or "Non disponible"
        direct_kpis = normalized.get("kpis") or {}
        direct_total = int(direct_kpis.get("total_scored") or 0)
        direct_anomalies = int(direct_kpis.get("anomalies") or 0)
        normalized["anomaly_distribution"] = payload.get("anomaly_distribution") or [
            ("Avec anomalie", direct_anomalies, TT_VIOLET),
            ("Sans anomalie", max(direct_total - direct_anomalies, 0), TT_TURQUOISE),
        ]
        direct_segment_colors = (TT_BLUE, TT_TURQUOISE, TT_VIOLET, TT_ORANGE, TT_YELLOW)
        normalized["segments"] = [
            (*item, direct_segment_colors[index % len(direct_segment_colors)]) if len(item) == 2 else item
            for index, item in enumerate(payload.get("segments") or [])
        ]
        return normalized

    kpis = payload.get("kpis") or {}
    report = payload.get("report") or {}
    filters = payload.get("filters") or {}
    total = int(kpis.get("total_clients") or 0)

    risk_distribution = [
        ("Risque eleve", int(kpis.get("clients_high") or 0), RISK_HIGH),
        ("Risque moyen", int(kpis.get("clients_medium") or 0), RISK_MEDIUM),
        ("Risque faible", int(kpis.get("clients_low") or 0), RISK_LOW),
    ]
    action_labels = {
        "call_center_priority": "Appel prioritaire",
        "sms_retention_offer": "SMS / retention",
        "monitor_only": "Suivi standard",
    }
    action_colors = {
        "call_center_priority": TT_RED,
        "sms_retention_offer": TT_BLUE,
        "monitor_only": TT_TURQUOISE,
    }
    recommended_actions = [
        (
            action_labels.get(key, _canvas_text(key).replace("_", " ").capitalize()),
            int(value or 0),
            action_colors.get(key, GRAY_600),
        )
        for key, value in sorted((kpis.get("distribution_by_action") or {}).items(), key=lambda item: int(item[1] or 0), reverse=True)
    ]
    segment_labels = {
        "Standard": "Standard",
        "Bon-payeur": "Bon payeur",
        "SUSPENDED": "Suspendu",
        "DISCONNECTED": "Deconnecte",
        "ON-HOLD": "En attente",
        "unknown": "Non defini",
    }
    segment_colors = {
        "Standard": TT_BLUE,
        "Bon-payeur": TT_TURQUOISE,
        "SUSPENDED": TT_VIOLET,
        "DISCONNECTED": TT_ORANGE,
        "ON-HOLD": TT_YELLOW,
    }
    segments = [
        (
            segment_labels.get(key, _canvas_text(key).replace("_", " ").capitalize()),
            int(value or 0),
            segment_colors.get(key, GRAY_600),
        )
        for key, value in sorted((kpis.get("distribution_by_segment") or {}).items(), key=lambda item: int(item[1] or 0), reverse=True)
    ]

    priorities = []
    priority_colors = (RISK_HIGH, RISK_MEDIUM, RISK_LOW)
    for index, item in enumerate((report.get("decision_support") or [])[:3]):
        priorities.append({
            "num": str(index + 1),
            "title": item.get("priority") or "Non disponible",
            "target": f"Cible : {item.get('target') or 'Non disponible'} - Objectif : {item.get('business_goal') or 'Non disponible'}",
            "body": item.get("recommended_focus") or "Non disponible",
            "color": priority_colors[index],
        })

    findings = [_canvas_text(item) for item in (report.get("main_findings") or [])[:5]]
    recommendations = []
    for index, item in enumerate((report.get("business_recommendations") or [])[:4], 1):
        if isinstance(item, str):
            item = {"title": item, "why": "Non disponible", "example": "Non disponible", "expected_impact": "Non disponible"}
        recommendations.append({
            "num": f"{index:02d}",
            "title": item.get("title") or "Non disponible",
            "why": item.get("why") or "Non disponible",
            "example": item.get("example") or "Non disponible",
            "impact": item.get("expected_impact") or "Non disponible",
        })

    filter_labels = {
        "risk_tier": {"high": "Risque eleve", "medium": "Risque moyen", "low": "Risque faible"},
        "is_anomaly": {True: "Avec anomalie", False: "Sans anomalie"},
        "recommended_action": action_labels,
    }
    active_filters = []
    for key, value in filters.items():
        if value in (None, ""):
            continue
        label = {
            "risk_tier": "Niveau de risque",
            "cluster_name": "Segment",
            "is_anomaly": "Situation",
            "recommended_action": "Action",
            "search": "MSISDN",
        }.get(key, key)
        display = filter_labels.get(key, {}).get(value, segment_labels.get(value, value))
        active_filters.append(f"{label} : {_canvas_text(display)}")

    return {
        "generated_at": payload.get("generated_at") or datetime.now().astimezone().isoformat(),
        "scope": payload.get("scope") or ("filtered" if active_filters else "global"),
        "scope_display": "Clients filtres" if active_filters else "Tous les clients",
        "title": report.get("report_title") or "Non disponible",
        "subtitle": kpis.get("filter_summary") or ("Clients filtres" if active_filters else "Tous les clients"),
        "executive_summary": report.get("executive_summary") or "Non disponible",
        "confidentiality": payload.get("confidentiality") or "Non disponible",
        "filters": filters,
        "filters_display": ", ".join(active_filters) if active_filters else "Aucun filtre actif",
        "kpis": {
            "total_scored": total,
            "high_risk": int(kpis.get("clients_high") or 0),
            "medium_risk": int(kpis.get("clients_medium") or 0),
            "low_risk": int(kpis.get("clients_low") or 0),
            "anomalies": int(kpis.get("clients_with_anomaly") or 0),
            "average_score": kpis.get("average_risk_score"),
        },
        "risk_distribution": risk_distribution,
        "anomaly_distribution": [
            ("Avec anomalie", int(kpis.get("clients_with_anomaly") or 0), TT_VIOLET),
            ("Sans anomalie", max(total - int(kpis.get("clients_with_anomaly") or 0), 0), TT_TURQUOISE),
        ],
        "recommended_actions": recommended_actions,
        "segments": segments,
        "priorities": priorities,
        "findings": findings,
        "recommendations": recommendations,
    }


def generate_bad_debts_report(data: dict[str, Any], output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(build_bad_debts_pdf(data))
    return target


def build_bad_debts_pdf(payload: dict[str, Any]) -> bytes:
    data = normalize_bad_debts_report_data(payload)
    kpis = data["kpis"]
    total = int(kpis["total_scored"] or 0)
    available_width = A4[0] - 40 * mm
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=15 * mm,
        title=data["title"],
        author="Tunisie Telecom",
    )

    generated = data.get("generated_at")
    try:
        report_date = datetime.fromisoformat(str(generated).replace("Z", "+00:00")).strftime("%d / %m / %Y")
    except (TypeError, ValueError):
        report_date = datetime.now().strftime("%d / %m / %Y")

    title_copy = [
        _paragraph(data["title"], S_MAIN_TITLE),
        _paragraph(data["subtitle"], S_MAIN_SUB),
    ]
    if TT_LOGO_FILE.exists():
        logo_width = 22.5 * mm
        logo_column_width = 27 * mm
        title_block = Table(
            [["", title_copy, Image(str(TT_LOGO_FILE), width=logo_width, height=12.4 * mm, kind="proportional")]],
            colWidths=[logo_column_width, available_width - 2 * logo_column_width, logo_column_width],
        )
        title_block.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (1, 0), (1, 0), "CENTER"),
            ("ALIGN", (2, 0), (2, 0), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        story: list[Any] = [title_block, SP(1), MulticolorLine(available_width), SP(3)]
    else:
        story = [*title_copy, SP(1), MulticolorLine(available_width), SP(3)]
    meta = Table(
        [[_paragraph(data["scope_display"], S_LABEL), _paragraph(report_date, S_CENTER), _paragraph(data["confidentiality"], S_LABEL)]],
        colWidths=[available_width / 3] * 3,
    )
    meta.setStyle(TableStyle([
        ("ALIGN", (0, 0), (0, 0), "LEFT"),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ("ALIGN", (2, 0), (2, 0), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.extend([
        meta,
        SP(2),
        _paragraph(f"Filtres actifs : {data['filters_display']}", S_SUB),
        SP(3),
        _summary_card(data["executive_summary"], available_width),
        SP(4),
        HRFlowable(width="100%", thickness=1, color=TT_BLUE),
        SP(4),
    ])
    story.extend([_section_heading("Indicateurs cles", available_width), SP(3)])

    kpi_width = available_width / 6
    kpi_height = 23 * mm
    kpi_items = [
        MiniKPI(_number(kpis["total_scored"]), "Clients scores", "Perimetre analyse", TT_BLUE, kpi_width, kpi_height),
        MiniKPI(_number(kpis["high_risk"]), "Risque eleve", "Traitement prioritaire", RISK_HIGH, kpi_width, kpi_height),
        MiniKPI(_number(kpis["medium_risk"]), "Risque moyen", "Surveillance renforcee", RISK_MEDIUM, kpi_width, kpi_height),
        MiniKPI(_number(kpis["low_risk"]), "Risque faible", "Suivi standard", RISK_LOW, kpi_width, kpi_height),
        MiniKPI(_number(kpis["anomalies"]), "Anomalies", "Signal complementaire", TT_VIOLET, kpi_width, kpi_height),
        MiniKPI(_score(kpis["average_score"]), "Score moyen", "Score agrege", TT_TURQUOISE, kpi_width, kpi_height),
    ]
    kpi_grid = Table([kpi_items], colWidths=[kpi_width] * 6, rowHeights=[kpi_height])
    kpi_grid.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.extend([kpi_grid, SP(4), HRFlowable(width="100%", thickness=0.5, color=GRAY_300), SP(4)])
    story.extend([_section_heading("Graphes de pilotage", available_width), SP(3)])

    half_width = available_width / 2 - 2 * mm
    risk_items = [(label, _number(value), _pct(value, total), color) for label, value, color in data["risk_distribution"]]
    anomaly_items = [(label, _number(value), _pct(value, total), color) for label, value, color in data["anomaly_distribution"]]
    action_items = [(label, _number(value), _pct(value, total), color) for label, value, color in data["recommended_actions"]]
    segment_values = data["segments"][:3]
    segment_items = [(label, _number(value), _pct(value, total), color) for label, value, color in segment_values]
    chart_grid = Table(
        [
            [_chart_card("Repartition du risque", risk_items, half_width), _chart_card("Anomalies detectees", anomaly_items, half_width)],
            [_chart_card("Actions recommandees", action_items, half_width), _chart_card("Top segments", segment_items, half_width)],
        ],
        colWidths=[available_width / 2] * 2,
    )
    chart_grid.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4 * mm),
    ]))
    story.extend([chart_grid, PageBreak()])

    story.extend([
        _paragraph("Priorites & Recommandations", S_TITLE),
        SP(1),
        _paragraph("Orientations operationnelles issues du scoring ML", S_SUB),
        SP(1),
        MulticolorLine(available_width),
        SP(3),
        HRFlowable(width="100%", thickness=1, color=TT_BLUE),
        SP(5),
        _section_heading("Priorites d'action", available_width),
        SP(3),
    ])

    for item in data["priorities"]:
        story.extend([PriorityRow(item["num"], item["title"], item["target"], item["body"], item["color"], available_width), HRFlowable(width="100%", thickness=0.5, color=GRAY_300), SP(2)])

    story.extend([SP(2), _section_heading("Constats principaux", available_width), SP(2)])
    findings = [f"- {finding}" for finding in data["findings"]]
    finding_style = style("finding", fontSize=8.5, textColor=GRAY_600, leading=12, leftIndent=4 * mm)
    for finding in findings:
        story.extend([_paragraph(finding, finding_style), SP(1)])

    story.extend([SP(2), HRFlowable(width="100%", thickness=0.5, color=GRAY_300), SP(4)])
    story.extend([_section_heading("Recommandations operationnelles", available_width), SP(3)])
    rec_width = available_width / 2 - 2 * mm
    recommendations = [
        RecBlock(item["num"], item["title"], item["why"], item["example"], item["impact"], rec_width, TT_PALETTE[index % len(TT_PALETTE)])
        for index, item in enumerate(data["recommendations"])
    ]
    if recommendations:
        while len(recommendations) % 2:
            recommendations.append(Spacer(1, 1))
        rec_rows = [recommendations[index:index + 2] for index in range(0, len(recommendations), 2)]
        rec_grid = Table(rec_rows, colWidths=[available_width / 2] * 2, rowHeights=[44 * mm] * len(rec_rows))
        rec_grid.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4 * mm),
        ]))
        story.extend([rec_grid, SP(3)])
    else:
        story.extend([_paragraph("Aucune recommandation disponible pour ce perimetre.", S_BODY), SP(3)])
    doc.build(story, onFirstPage=_decorate_page, onLaterPages=_decorate_page)
    return buffer.getvalue()
