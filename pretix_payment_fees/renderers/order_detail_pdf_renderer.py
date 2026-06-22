"""
PDF renderer for the "Détail par commande" export (STORY-201).

Reuses the sober editorial style helpers of recette_pdf_renderer (palette,
fonts, euro formatting, header band, table style). One row per order. A4
landscape because the order table can be wide.

No personal data is rendered (the builder never provides any).
"""
import io

from django.utils.translation import gettext_lazy as _

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from reportlab.lib import colors as _colors

from .recette_pdf_renderer import (
    ACCENT,
    ACCENT_DARK,
    INK,
    MUTED,
    RULE,
    ZERO,
    _auto_widths,
    _FONT,
    _FONT_BD,
    _register_fonts,
    euro,
)

# Divider between orders: darker than the light inner rule so each order is
# clearly delimited.
ORDER_DIVIDER = _colors.HexColor("#B8BCC4")

# Landscape content width (A4 rotated, 10mm margins each side).
_DOC_W = A4[1] - 20 * mm

OL = {
    "title": _("Détail par commande"),
    "organizer": _("Organisateur"),
    "event": _("Événement"),
    "generated": _("Édité le"),
    "currency": _("Devise"),
    "order": _("Commande"),
    "od_date": _("Date et heure"),
    "channel": _("Canal de vente"),
    "count": _("Places"),
    "product": _("Produit"),
    "qty": _("Qté"),
    "gross": _("Montant"),
    "net": _("Net"),
    "total": _("Total"),
    "orders": _("commandes"),
}


class OrderDetailPDFRenderer:
    """Render an OrderDetailReport to PDF bytes (landscape, sober style)."""

    def __init__(self, report, event_meta=None):
        self.report = report
        self.meta = event_meta or {}
        _register_fonts()

    def render(self) -> bytes:
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf, pagesize=landscape(A4),
            leftMargin=10 * mm, rightMargin=10 * mm,
            topMargin=12 * mm, bottomMargin=12 * mm,
            title=str(OL["title"]),
        )
        story = self._header()
        story.append(self._table())
        doc.build(story)
        return buf.getvalue()

    def _styles(self):
        base = getSampleStyleSheet()
        return {
            "title": ParagraphStyle(
                "t", parent=base["Title"], fontName=_FONT_BD, fontSize=18,
                textColor=ACCENT_DARK, spaceAfter=2, leading=21),
            "sub": ParagraphStyle(
                "s", parent=base["Normal"], fontName=_FONT, fontSize=8.5,
                textColor=MUTED, leading=12),
        }

    def _header(self):
        s = self._styles()
        m = self.meta
        story = [Paragraph(str(OL["title"]), s["title"])]
        bits = []
        if m.get("organizer"):
            bits.append(f"{m['organizer']}")
        if m.get("event"):
            ev = m["event"]
            if m.get("slug"):
                ev = f"{ev} ({m['slug']})"
            bits.append(ev)
        info = []
        cur = self.report.currency or "EUR"
        info.append(f"{OL['currency']} {cur}")
        if m.get("generated"):
            info.append(f"{OL['generated']} {m['generated']}")
        info.append(f"{self.report.order_count} {OL['orders']}")
        line1 = "  ·  ".join(bits)
        line2 = "  ·  ".join(str(x) for x in info)
        html = "<br/>".join(x for x in (line1, line2) if x)
        if html:
            story.append(Paragraph(html, s["sub"]))
        rule = Table([[""]], colWidths=[_DOC_W], rowHeights=[1.4])
        rule.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, -1), 1.4, ACCENT),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        story += [Spacer(0, 3 * mm), rule, Spacer(0, 4 * mm)]
        return story

    def _header_row(self):
        head = [str(OL["order"]), str(OL["od_date"]), str(OL["channel"]),
                str(OL["product"]), str(OL["qty"]), str(OL["gross"])]
        head += [c.label for c in self.report.fee_columns]
        head += [str(OL["net"])]
        return head

    def _table(self):
        data = [self._header_row()]
        order_end_rows = []   # last data-row index of each order (for dividers)
        nfee = len(self.report.fee_columns)
        for r in self.report.rows:
            date = r.datetime.strftime("%d/%m/%Y %H:%M") if r.datetime else ""
            for i, ln in enumerate(r.lines):
                first = i == 0
                fee_cells = [euro(ln.fees.get(c.key, ZERO))
                             for c in self.report.fee_columns]
                data.append([
                    r.code if first else "",
                    date if first else "",
                    r.channel if first else "",
                    ln.product, str(ln.count), euro(ln.gross),
                    *fee_cells, euro(ln.net),
                ])
            order_end_rows.append(len(data) - 1)

        # grand total row
        rep = self.report
        fee_tot = [euro(rep.fees.get(c.key, ZERO)) for c in rep.fee_columns]
        data.append([
            str(OL["total"]), "", "", "", str(rep.count), euro(rep.gross),
            *fee_tot, euro(rep.net),
        ])
        total_row = len(data) - 1

        widths = _auto_widths(data, size=7.5, max_first=24 * mm)
        # stretch the "Produit" column (index 3) so the table spans the page
        gap = _DOC_W - sum(widths)
        if gap > 0 and len(widths) > 3:
            widths[3] += gap
        t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
        style = [
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("FONTNAME", (0, 0), (-1, -1), _FONT),
            ("TEXTCOLOR", (0, 1), (-1, -1), INK),
            ("FONTNAME", (0, 0), (-1, 0), _FONT_BD),
            ("FONTSIZE", (0, 0), (-1, 0), 6.5),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#8A8F98")),
            ("LINEBELOW", (0, 0), (-1, 0), 1.0, ACCENT),
            ("ALIGN", (4, 0), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            # total row
            ("FONTNAME", (0, total_row), (-1, total_row), _FONT_BD),
            ("TEXTCOLOR", (0, total_row), (-1, total_row), ACCENT_DARK),
            ("LINEABOVE", (0, total_row), (-1, total_row), 1.0, ACCENT),
            ("TOPPADDING", (0, total_row), (-1, total_row), 6),
        ]
        # divider only BETWEEN orders (after each order's last line), not
        # between the product lines of the same order; darker so each order
        # stands out clearly
        for end in order_end_rows[:-1] if order_end_rows else []:
            style.append(("LINEBELOW", (0, end), (-1, end), 0.6, ORDER_DIVIDER))
        t.setStyle(TableStyle(style))
        return t
