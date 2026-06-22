#!/usr/bin/env python3
"""
Mock generator for the "Sales revenue report" export (Recette Manifestation).

Standalone (no Django) - produces a sample PDF with REAL data extracted from
the pretix-dev database (organizer "Gosselico", event "Les Détonantes #2").

Design choices (validated with goss):
- Pretix vocabulary, not Trium vocabulary (Product / Gross / Tax / Paid ...).
- Fee columns are dynamic: one column per OrderFee type present in the data.
- Column widths auto-fit content (no overflow).
- Sales-channel sections + grand total across channels.
- No em dashes anywhere (project rule).

Run inside the pretix-dev container:
    sed 's#OUT = ".*"#OUT = "/tmp/out.pdf"#' mock_recette_manifestation.py \\
      | docker exec -i pretix-dev python3 -
    docker cp pretix-dev:/tmp/out.pdf docs/mock_recette_manifestation.pdf
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4  # portrait by default
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

OUT = "/plugins/pretix-payment-fees/docs/mock_recette_manifestation.pdf"

# ---------------------------------------------------------------------------
# Fonts: register Pretix's OpenSans (full Unicode -> accents render correctly).
# The default reportlab Helvetica does NOT render accented glyphs.
# ---------------------------------------------------------------------------
_FONT = "Helvetica"        # fallbacks if OpenSans is unavailable
_FONT_BD = "Helvetica-Bold"
_OPENSANS_REG = "/pretix/src/pretix/static/fonts/OpenSans-Regular.ttf"
_OPENSANS_BD = "/pretix/src/pretix/static/fonts/OpenSans-Bold.ttf"
try:
    import os
    reg = _OPENSANS_REG if os.path.exists(_OPENSANS_REG) else \
        "/pretix/src/pretix/static/fonts/opensans_regular_macroman/OpenSans-Regular-webfont.ttf"
    bd = _OPENSANS_BD if os.path.exists(_OPENSANS_BD) else \
        "/pretix/src/pretix/static/fonts/opensans_bold_macroman/OpenSans-Bold-webfont.ttf"
    pdfmetrics.registerFont(TTFont("OpenSans", reg))
    pdfmetrics.registerFont(TTFont("OpenSans-Bold", bd))
    _FONT, _FONT_BD = "OpenSans", "OpenSans-Bold"
except Exception as e:  # pragma: no cover
    print(f"[warn] OpenSans not registered, using Helvetica: {e}")

# ===========================================================================
# REAL data extracted from pretix-dev (event slug: detonantes-2, paid orders).
# Real PSP fees: 26.93 EUR (Mollie creditcard) - web channel only. Tax: 0.00%.
# Raw rows: (product, qty, unit_price, gross_revenue)
# ===========================================================================
_WEB_RAW = [
    ("Tarif plein", 46, 20.00, 920.00),
    ("Tarif étudiant / demandeur d'emploi", 12, 17.00, 204.00),
    ("Destination Rennes - Plein tarif", 19, 20.00, 380.00),
    ("Destination Rennes - Réduit", 9, 17.00, 153.00),
    ("Destination Rennes - Sortir", 12, 8.50, 102.00),
    ("Destination Rennes - Early Bird", 3, 16.00, 48.00),
    ("Early Bird", 7, 16.00, 112.00),
    ("Enfant -12 ans", 1, 0.00, 0.00),
]
_GUICHET_RAW = [
    ("Tarif plein", 27, 20.00, 540.00),
    ("Tarif étudiant / demandeur d'emploi", 6, 17.00, 102.00),
    ("Tarif Sortir !", 2, 8.50, 17.00),
    ("Invitation", 37, 0.00, 0.00),
]
# PSP fees per channel, keyed by OrderFee.internal_type (real Pretix values).
# Option 2: ONE COLUMN PER PSP (per internal_type), generated dynamically.
# Web: real Mollie 26.93 EUR. Guichet: illustrative SumUp 3.25 EUR (real value
# observed on another event) to demonstrate the second dynamic PSP column.
_PSP_WEB = {"mollie_creditcard_fee": 26.93}
_PSP_GUICHET = {"sumup_fee": 3.25}

# Human-readable labels for known PSP internal_types. The real exporter derives
# the column set from the internal_types actually found in the data; any unknown
# type falls back to a humanized label (see psp_label()).
PSP_LABELS = {
    "mollie_creditcard_fee": "Frais Mollie (CB)",
    "mollie_ideal_fee": "Frais Mollie (iDEAL)",
    "mollie_bancontact_fee": "Frais Mollie (Bancontact)",
    "sumup_fee": "Frais SumUp",
}

CURRENCY = "EUR"
CURRENCY_SYMBOL = "€"  # euro sign


def psp_label(internal_type):
    """Readable column label for a PSP internal_type, with humanized fallback."""
    if internal_type in PSP_LABELS:
        return PSP_LABELS[internal_type]
    base = internal_type.replace("_fee", "").replace("_", " ").strip()
    return "Frais " + base.title()


def euro(v):
    """Format a monetary value FR style with currency symbol (1 234,56 EUR)."""
    if v is None or v == "":
        return ""
    s = f"{v:,.2f}".replace(",", " ").replace(".", ",")
    return f"{s} {CURRENCY_SYMBOL}"


def qty(v):
    """Plain integer/count, no currency."""
    return str(v)


def _spread_psp(raw, psp_by_type):
    """Spread each PSP fee total across paying rows, pro rata of gross revenue.

    psp_by_type: {internal_type: total_amount}. Returns rows as dicts:
        product, qty, unit_price, gross, fees{internal_type: amount}.
    """
    base = sum(r[3] for r in raw)
    paying = [r for r in raw if r[3] > 0]
    rows = []
    acc = {k: 0.0 for k in psp_by_type}
    for r in raw:
        product, q, pu, gross = r
        fees = {}
        for itype, total in psp_by_type.items():
            if gross > 0 and base > 0:
                if r is paying[-1]:
                    fees[itype] = round(total - acc[itype], 2)  # last row balances
                else:
                    fees[itype] = round(total * gross / base, 2)
                    acc[itype] += fees[itype]
            else:
                fees[itype] = 0.0
        rows.append({"product": product, "qty": q, "unit_price": pu,
                     "gross": gross, "fees": fees})
    return rows


CHANNELS = [
    {
        "name": "Boutique en ligne",       # Pretix sales channel "web" label (fr)
        "tax_rate": "0,00 %",
        "rows": _spread_psp(_WEB_RAW, _PSP_WEB),
    },
    {
        "name": "Guichet",                  # Pretix sales channel "api.guichet"
        "tax_rate": "0,00 %",
        "rows": _spread_psp(_GUICHET_RAW, _PSP_GUICHET),
    },
]


# Dynamic fee columns: union of all PSP internal_types present across channels,
# in first-seen order. This is what the real exporter computes from the data.
def _collect_fee_columns(channels):
    seen = []
    for ch in channels:
        for row in ch["rows"]:
            for itype in row["fees"]:
                if itype not in seen:
                    seen.append(itype)
    return [{"key": k, "label": psp_label(k)} for k in seen]


FEE_COLUMNS = _collect_fee_columns(CHANNELS)

EVENT = {
    "organizer": "Gosselico",
    "name": "Les Détonantes #2",
    "slug": "detonantes-2",
    "date": "06/09/2025 18:00",
    "location": "Salle de la Cité, 10 Rue Saint-Louis 35000 Rennes",
    "edited": "22/06/2026",
}


# ---------------------------------------------------------------------------
# Table building (Pretix vocabulary)
# Columns: Product | Count | Unit price | Gross | <fee cols...> | Net revenue
#   - "Net revenue" here = gross minus fees (revenue kept after PSP fees)
#   - one TOTAL row per channel; no duplicate row for single-line products
# ---------------------------------------------------------------------------
def build_header():
    head = ["Produit", "Quantité", "Prix unitaire", "Brut"]
    head += [c["label"] for c in FEE_COLUMNS]
    head += ["Recette nette"]
    return head


def build_channel_rows(rows):
    data = [build_header()]
    tot = {"qty": 0, "gross": 0.0, "net": 0.0,
           "fees": {c["key"]: 0.0 for c in FEE_COLUMNS}}
    for r in rows:
        fee_sum = sum(r["fees"].get(c["key"], 0.0) for c in FEE_COLUMNS)
        net = r["gross"] - fee_sum
        line = [r["product"], str(r["qty"]), euro(r["unit_price"]), euro(r["gross"])]
        line += [euro(r["fees"].get(c["key"], 0.0)) for c in FEE_COLUMNS]
        line += [euro(net)]
        data.append(line)
        tot["qty"] += r["qty"]
        tot["gross"] += r["gross"]
        tot["net"] += net
        for c in FEE_COLUMNS:
            tot["fees"][c["key"]] += r["fees"].get(c["key"], 0.0)
    # single TOTAL row for the channel
    total_line = ["TOTAL", str(tot["qty"]), "", euro(tot["gross"])]
    total_line += [euro(tot["fees"][c["key"]]) for c in FEE_COLUMNS]
    total_line += [euro(tot["net"])]
    data.append(total_line)
    return data, tot


def auto_widths(data, size=8, padding=6, min_w=12 * mm, max_first=55 * mm):
    """Compute per-column widths that fit the widest cell (no overflow)."""
    ncols = len(data[0])
    widths = []
    for ci in range(ncols):
        w = 0
        for row in data:
            txt = str(row[ci]) if ci < len(row) else ""
            fnt = _FONT_BD if row is data[0] else _FONT
            w = max(w, stringWidth(txt, fnt, size))
        w += padding * 2
        if ci == 0:
            w = min(max(w, min_w), max_first)
        else:
            w = max(w, min_w)
        widths.append(w)
    return widths


def main():
    doc = SimpleDocTemplate(
        OUT, pagesize=A4,  # portrait to save paper
        leftMargin=10 * mm, rightMargin=10 * mm,
        topMargin=12 * mm, bottomMargin=12 * mm,
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontName=_FONT_BD,
                        fontSize=15, spaceAfter=2)
    meta = ParagraphStyle("meta", parent=styles["Normal"], fontName=_FONT,
                          fontSize=8.5, leading=12)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontName=_FONT_BD,
                        fontSize=10.5, spaceBefore=8)
    note = ParagraphStyle("note", parent=styles["Normal"], fontName=_FONT,
                          fontSize=7, textColor=colors.grey, leading=9)

    story = [Paragraph("Rapport de recette", h1)]
    story.append(Paragraph(
        f"<b>Organisateur :</b> {EVENT['organizer']} &nbsp;|&nbsp; "
        f"<b>Événement :</b> {EVENT['name']} ({EVENT['slug']})<br/>"
        f"<b>Date :</b> {EVENT['date']} &nbsp;|&nbsp; "
        f"<b>Lieu :</b> {EVENT['location']}<br/>"
        f"<b>Devise :</b> {CURRENCY} &nbsp;|&nbsp; "
        f"<b>Édité le :</b> {EVENT['edited']} "
        f"<i>(données réelles pretix-dev, maquette de mise en page)</i>", meta))
    story.append(Spacer(0, 4 * mm))

    base_style = [
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTNAME", (0, 0), (-1, -1), _FONT),
        ("FONTNAME", (0, 0), (-1, 0), _FONT_BD),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#404040")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#999999")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]

    grand = {"qty": 0, "gross": 0.0, "net": 0.0,
             "fees": {c["key"]: 0.0 for c in FEE_COLUMNS}}

    for ch in CHANNELS:
        story.append(Paragraph(
            f"Canal de vente : <b>{ch['name']}</b> "
            f"(taux de TVA {ch['tax_rate']})", h2))
        story.append(Spacer(0, 2 * mm))
        data, tot = build_channel_rows(ch["rows"])
        widths = auto_widths(data)
        t = Table(data, colWidths=widths, repeatRows=1)
        last = len(data) - 1
        t.setStyle(TableStyle(base_style + [
            ("BACKGROUND", (0, last), (-1, last), colors.HexColor("#bfbfbf")),
            ("FONTNAME", (0, last), (-1, last), _FONT_BD),
        ]))
        story.append(t)
        story.append(Spacer(0, 6 * mm))
        grand["qty"] += tot["qty"]
        grand["gross"] += tot["gross"]
        grand["net"] += tot["net"]
        for c in FEE_COLUMNS:
            grand["fees"][c["key"]] += tot["fees"][c["key"]]

    # Grand total across all channels
    story.append(Paragraph("Total tous canaux de vente", h2))
    gt_head = ["", "Quantité", "Brut"] + [c["label"] for c in FEE_COLUMNS] + ["Recette nette"]
    gt_row = ["TOTAL", str(grand["qty"]), euro(grand["gross"])]
    gt_row += [euro(grand["fees"][c["key"]]) for c in FEE_COLUMNS]
    gt_row += [euro(grand["net"])]
    gt_data = [gt_head, gt_row]
    gt_widths = auto_widths(gt_data, size=8)
    tt = Table(gt_data, colWidths=gt_widths)
    tt.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTNAME", (0, 0), (-1, -1), _FONT_BD),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#404040")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#bfbfbf")),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#999999")),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(tt)

    story.append(Spacer(0, 8 * mm))
    story.append(Paragraph(
        "Les colonnes de frais sont générées dynamiquement : une colonne par "
        "prestataire de paiement (PSP) réellement présent dans les données, "
        "identifié par le type interne de l'OrderFee Pretix (ici Mollie CB et "
        "SumUp). Recette nette = Brut moins les frais. Le vocabulaire suit les "
        "rapports natifs Pretix (Produit, Brut, Net, Quantité).", note))

    doc.build(story)
    print(f"PDF genere: {OUT}")


if __name__ == "__main__":
    main()
