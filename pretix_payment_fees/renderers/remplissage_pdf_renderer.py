"""
PDF renderer for the "Remplissage de salle" export (STORY-202).

Sober "venue sheet": a category-count table + a quota fill table (sold /
capacity / rate). No monetary value anywhere. Reuses the style helpers of
recette_pdf_renderer. A4 portrait.
"""
import io

from django.utils.translation import gettext_lazy as _

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .recette_pdf_renderer import (
    ACCENT,
    ACCENT_DARK,
    INK,
    MUTED,
    RULE,
    _auto_widths,
    _FONT,
    _FONT_BD,
    _register_fonts,
    doc_width,
)


def _stretch_first(widths, target):
    """Widen the first column so the table spans `target` (left-anchored)."""
    total = sum(widths)
    if total < target and widths:
        widths = list(widths)
        widths[0] += target - total
    return widths

RL = {
    "title": _("Remplissage de salle"),
    "generated": _("Édité le"),
    "places": _("places vendues"),
    "categories": _("Ventes par catégorie"),
    "quotas": _("Taux de remplissage"),
    "product": _("Catégorie"),
    "paid": _("Payant"),
    "invitations": _("Invitations"),
    "total": _("Total"),
    "quota": _("Quota"),
    "sold": _("Vendu"),
    "capacity": _("Capacité"),
    "rate": _("Remplissage"),
}


class RemplissagePDFRenderer:
    def __init__(self, report, event_meta=None):
        self.report = report
        self.meta = event_meta or {}
        _register_fonts()

    def render(self) -> bytes:
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf, pagesize=A4,
            leftMargin=10 * mm, rightMargin=10 * mm,
            topMargin=12 * mm, bottomMargin=12 * mm,
            title=str(RL["title"]),
        )
        story = self._header()
        story += self._categories_block()
        story += self._quotas_block()
        doc.build(story)
        return buf.getvalue()

    def _styles(self):
        base = getSampleStyleSheet()
        return {
            "title": ParagraphStyle(
                "t", parent=base["Title"], fontName=_FONT_BD, fontSize=19,
                textColor=ACCENT_DARK, spaceAfter=2, leading=22),
            "sub": ParagraphStyle(
                "s", parent=base["Normal"], fontName=_FONT, fontSize=8.5,
                textColor=MUTED, leading=12),
            "h2": ParagraphStyle(
                "h2", parent=base["Heading2"], fontName=_FONT_BD, fontSize=11,
                textColor=INK, spaceBefore=12, spaceAfter=2),
        }

    def _header(self):
        s = self._styles()
        m = self.meta
        story = [Paragraph(str(RL["title"]), s["title"])]
        bits = []
        if m.get("organizer"):
            bits.append(m["organizer"])
        if m.get("event"):
            ev = m["event"]
            if m.get("slug"):
                ev = f"{ev} ({m['slug']})"
            bits.append(ev)
        info = list(bits)
        if m.get("date"):
            info.append(m["date"])
        info.append(f"{self.report.total_places} {RL['places']}")
        if m.get("generated"):
            info.append(f"{RL['generated']} {m['generated']}")
        html = "  ·  ".join(str(x) for x in info)
        if html:
            story.append(Paragraph(html, s["sub"]))
        rule = Table([[""]], colWidths=[doc_width()], rowHeights=[1.4])
        rule.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, -1), 1.4, ACCENT),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        story += [Spacer(0, 3 * mm), rule, Spacer(0, 4 * mm)]
        return story

    def _table_style(self, data, total_row=None):
        style = [
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("FONTNAME", (0, 0), (-1, -1), _FONT),
            ("TEXTCOLOR", (0, 1), (-1, -1), INK),
            ("FONTNAME", (0, 0), (-1, 0), _FONT_BD),
            ("FONTSIZE", (0, 0), (-1, 0), 7.5),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#8A8F98")),
            ("LINEBELOW", (0, 0), (-1, 0), 1.0, ACCENT),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("LINEBELOW", (0, 1), (-1, -2 if total_row else -1), 0.5, RULE),
        ]
        if total_row is not None:
            style += [
                ("FONTNAME", (0, total_row), (-1, total_row), _FONT_BD),
                ("TEXTCOLOR", (0, total_row), (-1, total_row), ACCENT_DARK),
                ("LINEABOVE", (0, total_row), (-1, total_row), 1.0, ACCENT),
                ("TOPPADDING", (0, total_row), (-1, total_row), 6),
            ]
        return style

    def _categories_block(self):
        s = self._styles()
        rep = self.report
        if not rep.categories:
            return []
        head = [str(RL["product"]), str(RL["paid"]),
                str(RL["invitations"]), str(RL["total"])]
        data = [head]
        for c in rep.categories:
            data.append([c.name, str(c.paid), str(c.free), str(c.total)])
        data.append([str(RL["total"]), str(rep.total_paid),
                     str(rep.total_free), str(rep.total_places)])
        total_row = len(data) - 1
        widths = _auto_widths(data, max_first=110 * mm)
        widths = _stretch_first(widths, doc_width() * 0.62)
        t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
        t.setStyle(TableStyle(self._table_style(data, total_row)))
        return [Paragraph(str(RL["categories"]), s["h2"]),
                Spacer(0, 1.5 * mm), t, Spacer(0, 6 * mm)]

    def _quotas_block(self):
        s = self._styles()
        rep = self.report
        if not rep.quotas:
            return []
        show_rate = rep.has_quota_sizes
        if show_rate:
            head = [str(RL["quota"]), str(RL["sold"]),
                    str(RL["capacity"]), str(RL["rate"])]
        else:
            head = [str(RL["quota"]), str(RL["sold"])]
        data = [head]
        for q in rep.quotas:
            if show_rate:
                cap = str(q.size) if q.size else "∞"
                data.append([q.name, str(q.sold), cap, q.rate_display])
            else:
                data.append([q.name, str(q.sold)])
        widths = _auto_widths(data, max_first=110 * mm)
        widths = _stretch_first(widths, doc_width() * 0.62)
        t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
        t.setStyle(TableStyle(self._table_style(data)))
        return [Paragraph(str(RL["quotas"]), s["h2"]),
                Spacer(0, 1.5 * mm), t, Spacer(0, 6 * mm)]
