from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..models import TZ, Event, SourceResult, Week
from .markdown import COMPACT, fmt_time

INK = colors.HexColor("#1f1e1d")
MUTED = colors.HexColor("#6b6a66")
ACCENT = colors.HexColor("#9a3412")
RULE = colors.HexColor("#d6d3cd")


def _styles():
    ss = getSampleStyleSheet()
    base = dict(fontName="Helvetica", textColor=INK)
    return {
        "title": ParagraphStyle("t", parent=ss["Title"], fontName="Helvetica-Bold", fontSize=20, leading=24, alignment=0, spaceAfter=2, textColor=INK),
        "sub": ParagraphStyle("s", fontSize=9, leading=12, textColor=MUTED, fontName="Helvetica", spaceAfter=10),
        "day": ParagraphStyle("d", fontName="Helvetica-Bold", fontSize=12.5, leading=16, textColor=ACCENT, spaceBefore=10, spaceAfter=4),
        "time": ParagraphStyle("tm", fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=INK),
        "ev": ParagraphStyle("e", fontSize=9.5, leading=12.5, **base),
        "meta": ParagraphStyle("m", fontSize=8.3, leading=11, textColor=MUTED, fontName="Helvetica"),
        "small": ParagraphStyle("sm", fontSize=8.3, leading=11, textColor=MUTED, fontName="Helvetica"),
        "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=INK, spaceBefore=14, spaceAfter=4),
    }


def _event_cell(e: Event, st) -> list:
    title = escape(e.title)
    if e.url:
        title = f'<link href="{escape(e.url)}" color="#1f1e1d">{title}</link>'
    parts = [Paragraph(f"<b>{title}</b>", st["ev"])]
    meta = " · ".join(escape(x) for x in [e.venue or e.address, e.category, e.price] if x)
    if meta:
        parts.append(Paragraph(meta, st["meta"]))
    if e.description:
        parts.append(Paragraph(escape(e.description[:240]), st["meta"]))
    for n in e.notes:
        parts.append(Paragraph(f"Note: {escape(n)}", st["meta"]))
    return parts


def render(path: str, week: Week, events: list[Event], results: list[SourceResult], warnings: list[str],
           generated: datetime | None = None) -> None:
    generated = generated or datetime.now(TZ)
    st = _styles()
    doc = SimpleDocTemplate(path, pagesize=letter, leftMargin=0.7 * inch, rightMargin=0.7 * inch,
                            topMargin=0.6 * inch, bottomMargin=0.6 * inch, title=f"Philly week of {week.label()}")
    flow = [Paragraph(f"Philly week of {escape(week.label())}", st["title"]),
            Paragraph(f"Generated {generated:%a %b %-d, %-I:%M %p} · {len(events)} events", st["sub"])]
    by_day = defaultdict(list)
    for e in events:
        by_day[e.day].append(e)
    for d in week.days():
        evs = by_day.get(d, [])
        main = [e for e in evs if e.category not in COMPACT]
        mics = [e for e in evs if e.category in COMPACT]
        rows = [[Paragraph(fmt_time(e), st["time"]), _event_cell(e, st)] for e in main]
        if mics:
            rows.append([Paragraph("Open mics", st["time"]),
                         Paragraph(escape(", ".join(f"{fmt_time(e)} {e.venue}" for e in mics)), st["meta"])])
        if not rows:
            rows = [["", Paragraph("Nothing listed.", st["meta"])]]
        t = Table(rows, colWidths=[0.85 * inch, 6.25 * inch])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ]))
        flow.append(KeepTogether([Paragraph(f"{d:%A, %b %-d}", st["day"]), t]) if len(rows) < 12
                    else Paragraph(f"{d:%A, %b %-d}", st["day"]))
        if len(rows) >= 12:
            flow.append(t)
    if warnings:
        flow.append(Paragraph("Heads up", st["h2"]))
        flow += [Paragraph(escape(w), st["small"]) for w in warnings]
    flow.append(Paragraph("Sources", st["h2"]))
    flow += [Paragraph(escape(f"{r.name}: {'ok' if r.ok else r.error} ({r.count})"), st["small"]) for r in results]
    doc.build(flow)
