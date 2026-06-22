"""
Shared tabular flattening for the "Recette Manifestation" export (STORY-105).

Turns a RecetteReport (from RecetteDataBuilder) into a flat list of rows that
the CSV and Excel renderers serialise identically. Keeping a single flattening
function guarantees CSV and Excel (and the PDF totals) stay in sync.

Each detail row carries: channel, session, product, nature, count, unit price,
gross, one cell per dynamic fee column, net revenue, plus a "kind" marker
(detail / subtotal / total / grand_total) so renderers can style rows.
"""
from decimal import Decimal

from django.utils.translation import gettext_lazy as _

# Column labels translated via gettext_lazy (source strings in French, resolved
# to the user's language at export time). Translations live in the .po files.
COLS = {
    "channel": _("Canal de vente"),
    "session": _("Séance"),
    "product": _("Produit"),
    "nature": _("Nature"),
    "count": _("Quantité"),
    "unit_price": _("Prix unitaire"),
    "gross": _("Brut"),
    "net": _("Recette nette"),
    "kind": _("Type de ligne"),
    "vat": _("Taux de TVA"),
}

KIND_DETAIL = "detail"
KIND_SUBTOTAL = "subtotal"
KIND_TOTAL = "total"
KIND_GRAND = "grand_total"

ZERO = Decimal("0.00")


def column_headers(report):
    """Ordered header labels (plain strings): fixed columns + dynamic fees."""
    head = [
        COLS["channel"], COLS["session"], COLS["product"], COLS["nature"],
        COLS["vat"], COLS["count"], COLS["unit_price"], COLS["gross"],
    ]
    head += [c.label for c in report.fee_columns]
    head += [COLS["net"], COLS["kind"]]
    # resolve lazy proxies to plain strings for csv/openpyxl writers
    return [str(h) for h in head]


def _fee_values(fees, report):
    return [fees.get(c.key, ZERO) for c in report.fee_columns]


def flatten(report):
    """Yield rows (lists) describing the whole report, in display order.

    Values are kept as Decimal/int/str (not formatted) so each renderer applies
    its own number formatting. Fee cells are blank (None) where a fee does not
    apply at that aggregation level.
    """
    rows = []
    nfee = len(report.fee_columns)
    blank_fees = [None] * nfee

    for ch in report.channels:
        for se in ch.sessions:
            vat = se.tax_rate_display
            for cat in se.categories:
                if cat.is_single_line:
                    line = cat.lines[0]
                    rows.append([
                        ch.label, se.label, cat.name, line.nature, vat,
                        line.count, line.unit_price, line.gross,
                        *blank_fees, line.gross, KIND_DETAIL,
                    ])
                else:
                    for line in cat.lines:
                        rows.append([
                            ch.label, se.label, cat.name, line.nature, vat,
                            line.count, line.unit_price, line.gross,
                            *blank_fees, line.gross, KIND_DETAIL,
                        ])
                    rows.append([
                        ch.label, se.label, cat.name, "", vat,
                        cat.count, None, cat.gross,
                        *blank_fees, cat.gross, KIND_SUBTOTAL,
                    ])
            # session total (carries the fee breakdown)
            rows.append([
                ch.label, se.label, "", "", vat,
                se.count, None, se.gross,
                *_fee_values(se.fees, report), se.net, KIND_TOTAL,
            ])

    # grand total across all channels
    rows.append([
        "", "", "", "", "",
        report.count, None, report.gross,
        *_fee_values(report.fees, report), report.net, KIND_GRAND,
    ])
    return rows
