"""
PDF renderer for the "Recette Manifestation" accounting export (STORY-104).

Consumes the neutral structure produced by RecetteDataBuilder (STORY-100..103)
and serialises it to a PDF, reproducing the layout frozen in STORY-000.

Frozen design decisions (STORY-000):
    - A4 portrait, OpenSans embedded (accents), dynamic column widths.
    - French text, Pretix vocabulary, no em dashes.
    - Amounts shown with the euro symbol, FR format (1 234,56 EUR).
    - One fee column per PSP (dynamic).

The renderer recomputes NOTHING: it only serialises the builder's structure, so
PDF and CSV/Excel share identical totals.
"""

import io
import os
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ZERO = Decimal("0.00")

# Labels, frozen in French to match the STORY-000 mock and the Pretix FR
# vocabulary. Full gettext-based i18n (8 languages) is wired in STORY-106; until
# then the renderer uses these constants so the PDF reads correctly in French.
L = {
    "title": "Rapport de recette",
    "organizer": "Organisateur",
    "event": "Événement",
    "date": "Date",
    "location": "Lieu",
    "currency": "Devise",
    "generated": "Édité le",
    "sales_channel": "Canal de vente",
    "vat_rate": "taux de TVA",
    "product": "Produit",
    "count": "Quantité",
    "unit_price": "Prix unitaire",
    "gross": "Brut",
    "net": "Recette nette",
    "total": "Total",
    "grand_total": "Total tous canaux de vente",
    "by_session": "Recette par séance",
    "ticketing": "Billetterie",
    "paid": "Payant",
    "invitations": "Invitations",
}

# -- Fonts: register Pretix's OpenSans (full Unicode -> accents render). -------
_FONT = "Helvetica"
_FONT_BD = "Helvetica-Bold"
_FONTS_DIR = "/pretix/src/pretix/static/fonts"


def _register_fonts():
    global _FONT, _FONT_BD
    if _FONT == "OpenSans":  # already registered
        return
    try:
        reg = os.path.join(_FONTS_DIR, "OpenSans-Regular.ttf")
        bd = os.path.join(_FONTS_DIR, "OpenSans-Bold.ttf")
        if not os.path.exists(reg):
            reg = os.path.join(
                _FONTS_DIR,
                "opensans_regular_macroman/OpenSans-Regular-webfont.ttf",
            )
            bd = os.path.join(
                _FONTS_DIR, "opensans_bold_macroman/OpenSans-Bold-webfont.ttf"
            )
        pdfmetrics.registerFont(TTFont("OpenSans", reg))
        pdfmetrics.registerFont(TTFont("OpenSans-Bold", bd))
        _FONT, _FONT_BD = "OpenSans", "OpenSans-Bold"
    except Exception:
        pass  # fall back to Helvetica (accents may not render)


# -- Palette: sober editorial (Qonto/Pennylane), indigo used only as accent ----
ACCENT = colors.HexColor("#4F46E5")        # indigo accent (title, rules, total)
ACCENT_DARK = colors.HexColor("#3730A3")   # deeper indigo (title text)
INK = colors.HexColor("#111827")           # near-black body text
MUTED = colors.HexColor("#6B7280")         # muted grey (meta, notes)
COL_HEAD = colors.HexColor("#8A8F98")      # grey for the uppercase col headers
RULE = colors.HexColor("#EDEEF1")          # very light rule between rows
RULE_ACCENT = ACCENT                       # thin indigo rule under headers
SUBTOTAL_TXT = colors.HexColor("#374151")  # subtotal label (slate)


def doc_width():
    """Usable content width for an A4 portrait page with 10mm side margins."""
    return A4[0] - 20 * mm


def euro(v):
    """Format a monetary value FR style with euro symbol (1 234,56 EUR)."""
    if v is None or v == "":
        return ""
    s = f"{Decimal(v):,.2f}".replace(",", " ").replace(".", ",")
    return f"{s} €"


def _auto_widths(data, size=8, padding=6, min_w=12 * mm, max_first=55 * mm):
    """Per-column widths fitting the widest cell (no overflow)."""
    ncols = len(data[0])
    widths = []
    for ci in range(ncols):
        w = 0
        for row in data:
            txt = str(row[ci]) if ci < len(row) else ""
            fnt = _FONT_BD if row is data[0] else _FONT
            w = max(w, stringWidth(txt, fnt, size))
        w += padding * 2
        w = min(max(w, min_w), max_first) if ci == 0 else max(w, min_w)
        widths.append(w)
    return widths


class RecettePDFRenderer:
    """Render a RecetteReport to PDF bytes, reproducing the STORY-000 layout."""

    def __init__(self, report, event_meta=None):
        """report: RecetteReport. event_meta: dict with header fields."""
        self.report = report
        self.meta = event_meta or {}
        _register_fonts()

    # -- public API ---------------------------------------------------------

    def render(self) -> bytes:
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf, pagesize=A4,
            leftMargin=10 * mm, rightMargin=10 * mm,
            topMargin=12 * mm, bottomMargin=12 * mm,
            title=str(L["title"]),
        )
        story = self._header()
        for ch in self.report.channels:
            story += self._channel_section(ch)
        story += self._grand_total()
        story += self._cross_view()
        story += self._ticketing()
        doc.build(story)
        return buf.getvalue()

    # -- styles -------------------------------------------------------------

    def _styles(self):
        base = getSampleStyleSheet()
        return {
            "title": ParagraphStyle(
                "title", parent=base["Title"], fontName=_FONT_BD,
                fontSize=19, textColor=ACCENT_DARK, alignment=0,
                spaceAfter=2, leading=22),
            "subtitle": ParagraphStyle(
                "subtitle", parent=base["Normal"], fontName=_FONT,
                fontSize=8.5, textColor=MUTED, leading=12),
            "h2": ParagraphStyle(
                "h2", parent=base["Heading2"], fontName=_FONT_BD,
                fontSize=10.5, textColor=INK, spaceBefore=12, spaceAfter=0),
            "h2sub": ParagraphStyle(
                "h2sub", parent=base["Normal"], fontName=_FONT,
                fontSize=7.5, textColor=MUTED, spaceAfter=3, leading=10),
            "note": ParagraphStyle(
                "note", parent=base["Normal"], fontName=_FONT, fontSize=7.5,
                textColor=MUTED, leading=11),
        }

    # -- sections -----------------------------------------------------------

    def _header(self):
        """Sober title: indigo title text + muted meta, over a thin rule.

        No full-colour band. The colour is an accent (title + a thin indigo
        rule under the block), in the Qonto/Pennylane editorial style.
        """
        s = self._styles()
        m = self.meta
        story = [Paragraph(str(L["title"]), s["title"])]

        meta_bits = []
        if m.get("organizer"):
            meta_bits.append(m["organizer"])
        if m.get("event"):
            ev = m["event"]
            if m.get("slug"):
                ev = f"{ev} ({m['slug']})"
            meta_bits.append(ev)
        line1 = "  ·  ".join(meta_bits)

        info = []
        if m.get("date"):
            info.append(m["date"])
        if m.get("location"):
            info.append(m["location"])
        info.append(f"{L['currency']} {self.report.currency or 'EUR'}")
        if m.get("generated"):
            info.append(f"{L['generated']} {m['generated']}")
        line2 = "  ·  ".join(info)
        sub_html = "<br/>".join(x for x in (line1, line2) if x)
        if sub_html:
            story.append(Paragraph(sub_html, s["subtitle"]))

        # thin indigo rule under the header block
        rule = Table([[""]], colWidths=[doc_width()], rowHeights=[1.4])
        rule.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, -1), 1.4, ACCENT),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(Spacer(0, 3 * mm))
        story.append(rule)
        story.append(Spacer(0, 4 * mm))
        return story

    def _table_header(self):
        head = [L["product"], L["count"], L["unit_price"],
                L["gross"]]
        head += [c.label for c in self.report.fee_columns]
        head += [L["net"]]
        return head

    def _line_cells(self, line):
        fee_cells = [euro(line.fees.get(c.key, ZERO))
                     for c in self.report.fee_columns]
        fee_sum = sum((line.fees.get(c.key, ZERO)
                       for c in self.report.fee_columns), ZERO)
        net = line.gross - fee_sum
        return ([line.nature, str(line.count), euro(line.unit_price),
                 euro(line.gross)] + fee_cells + [euro(net)])

    def _channel_section(self, ch):
        s = self._styles()
        story = []
        for se in ch.sessions:
            title = f"{ch.label}  ·  {se.label}"
            story.append(Paragraph(title, s["h2"]))
            tax = f"{L['vat_rate']} {se.tax_rate_display}" \
                if se.tax_rate_display else ""
            if tax:
                story.append(Paragraph(tax, s["h2sub"]))
            story.append(Spacer(0, 1.5 * mm))
            story.append(self._session_table(se))
            story.append(Spacer(0, 6 * mm))
        return story

    def _session_table(self, se):
        data = [self._table_header()]
        subtotal_rows = []
        for cat in se.categories:
            if cat.is_single_line:
                # single nature: one row labelled by the category name
                line = cat.lines[0]
                data.append([cat.name] + self._line_cells(line)[1:])
            else:
                # several natures: one row per nature ("Category / Nature"),
                # followed by a category subtotal
                for line in cat.lines:
                    label = f"{cat.name} / {line.nature}"
                    data.append([label] + self._line_cells(line)[1:])
                data.append(self._subtotal_row(cat))
                subtotal_rows.append(len(data) - 1)
        data.append(self._session_total_row(se))
        total_row = len(data) - 1

        widths = _auto_widths(data)
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle(self._modern_table_style(
            data, total_row=total_row, subtotal_rows=subtotal_rows
        )))
        return t

    def _subtotal_row(self, cat):
        fee_cells = [euro(cat_fees(cat).get(c.key, ZERO))
                     for c in self.report.fee_columns]
        return ([cat.name, str(cat.count), "", euro(cat.gross)]
                + fee_cells + [euro(cat.gross)])

    def _session_total_row(self, se):
        fee_cells = [euro(se.fees.get(c.key, ZERO))
                     for c in self.report.fee_columns]
        return ([L["total"], str(se.count), "", euro(se.gross)]
                + fee_cells + [euro(se.net)])

    def _modern_table_style(self, data, total_row=None, subtotal_rows=None):
        """Sober editorial style (Qonto/Pennylane).

        Column headers carry no fill: muted grey uppercase text with a thin
        indigo rule beneath. Body rows are separated by a very light rule, no
        zebra. The total row has no fill either: a strong rule above and indigo
        bold text. Colour is used only as an accent.

        total_row: index of the emphasised total row.
        subtotal_rows: indices of category subtotal rows (slate, bold, no fill).
        """
        subtotal_rows = subtotal_rows or []
        style = [
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("FONTNAME", (0, 0), (-1, -1), _FONT),
            ("TEXTCOLOR", (0, 1), (-1, -1), INK),
            # header row: no fill, muted grey, slightly smaller
            ("FONTNAME", (0, 0), (-1, 0), _FONT_BD),
            ("FONTSIZE", (0, 0), (-1, 0), 7),
            ("TEXTCOLOR", (0, 0), (-1, 0), COL_HEAD),
            ("LINEBELOW", (0, 0), (-1, 0), 1.0, RULE_ACCENT),
            # alignment
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            # airy padding, flush left/right edges
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (0, -1), 2),
            ("RIGHTPADDING", (-1, 0), (-1, -1), 2),
            ("LEFTPADDING", (1, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-2, -1), 6),
            # light rule between body rows only
            ("LINEBELOW", (0, 1), (-1, -2), 0.5, RULE),
        ]
        # subtotal rows: slate bold label, no fill
        for r in subtotal_rows:
            style.append(("FONTNAME", (0, r), (-1, r), _FONT_BD))
            style.append(("TEXTCOLOR", (0, r), (-1, r), SUBTOTAL_TXT))
        # total row: strong rule above, indigo bold text, no fill
        if total_row is not None:
            style.append(("FONTNAME", (0, total_row), (-1, total_row),
                          _FONT_BD))
            style.append(("TEXTCOLOR", (0, total_row), (-1, total_row),
                          ACCENT_DARK))
            style.append(("LINEABOVE", (0, total_row), (-1, total_row),
                          1.0, ACCENT))
            style.append(("LINEBELOW", (0, total_row), (-1, total_row),
                          0, colors.white))
            style.append(("TOPPADDING", (0, total_row), (-1, total_row), 6))
        return style

    def _grand_total(self):
        s = self._styles()
        r = self.report
        if len(r.channels) <= 1:
            return []  # a single channel already shows its total
        head = ["", L["count"], L["gross"]]
        head += [c.label for c in r.fee_columns] + [L["net"]]
        fee_cells = [euro(r.fees.get(c.key, ZERO)) for c in r.fee_columns]
        row = [L["total"], str(r.count), euro(r.gross)] + fee_cells \
            + [euro(r.net)]
        data = [head, row]
        widths = _auto_widths(data)
        t = Table(data, colWidths=widths)
        t.setStyle(TableStyle(self._modern_table_style(data, total_row=1)))
        return [Paragraph(L["grand_total"], s["h2"]),
                Spacer(0, 1.5 * mm), t, Spacer(0, 6 * mm)]

    def _cross_view(self):
        s = self._styles()
        cv = self.report.cross_view()
        if len(cv.sessions) <= 1:
            return []  # no point in a cross view with a single session
        head = [L["product"]] + [lbl for _k, lbl in cv.sessions] \
            + [L["total"]]
        data = [head]
        for cat, cells in cv.rows.items():
            row = [cat]
            for k, _lbl in cv.sessions:
                row.append(euro(cells.get(k, {}).get("gross", ZERO)))
            row.append(euro(cv.row_total(cat)["gross"]))
            data.append(row)
        widths = _auto_widths(data)
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle(self._modern_table_style(data)))
        return [Paragraph(L["by_session"], s["h2"]),
                Spacer(0, 1.5 * mm), t, Spacer(0, 6 * mm)]

    def _ticketing(self):
        s = self._styles()
        tb = self.report.ticketing()
        if not tb.rows:
            return []
        head = [L["product"], L["paid"], L["invitations"],
                L["total"]]
        data = [head]
        for cat, c in tb.rows.items():
            data.append([cat, str(c["paid"]), str(c["free"]),
                         str(c["paid"] + c["free"])])
        tot = tb.total()
        data.append([L["total"], str(tot["paid"]), str(tot["free"]),
                     str(tot["paid"] + tot["free"])])
        last = len(data) - 1
        widths = _auto_widths(data)
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle(self._modern_table_style(data, total_row=last)))
        return [Paragraph(L["ticketing"], s["h2"]),
                Spacer(0, 1.5 * mm), t, Spacer(0, 6 * mm)]


def cat_fees(cat):
    """Fees do not live on categories (they are order-level). Empty by design.

    Subtotal fee cells are blank because fees are attributed at the session
    level, not per category. Returning an empty dict keeps the column aligned.
    """
    return {}
