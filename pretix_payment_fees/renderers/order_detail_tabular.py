"""
Tabular flattening + CSV/Excel renderers for the "Détail par commande" export
(STORY-201).

One row per order. Shares the FR format conventions of recette_tabular (UTF-8
BOM CSV with semicolons and decimal commas; real numeric cells in Excel). No
personal data.
"""
import csv
import io
from decimal import Decimal

from django.utils.translation import gettext_lazy as _

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

ZERO = Decimal("0.00")
BOM = "﻿"

OCOLS = {
    "order": _("Commande"),
    "date": _("Date et heure"),
    "channel": _("Canal de vente"),
    "product": _("Produit"),
    "qty": _("Qté"),
    "gross": _("Montant"),
    "net": _("Net"),
    "kind": _("Type de ligne"),
}


def column_headers(report):
    head = [OCOLS["order"], OCOLS["date"], OCOLS["channel"], OCOLS["product"],
            OCOLS["qty"], OCOLS["gross"]]
    head += [c.label for c in report.fee_columns]
    head += [OCOLS["net"], OCOLS["kind"]]
    return [str(h) for h in head]


def flatten(report):
    """Rows (lists): one per product line. The order code/date/channel are
    repeated on every line of the order (so CSV/Excel stay self-contained for
    filtering and pivots), plus a grand total."""
    rows = []
    for r in report.rows:
        date = r.datetime.strftime("%Y-%m-%d %H:%M") if r.datetime else ""
        for ln in r.lines:
            fee_vals = [ln.fees.get(c.key, ZERO) for c in report.fee_columns]
            rows.append([
                r.code, date, r.channel, ln.product, ln.count, ln.gross,
                *fee_vals, ln.net, "line",
            ])
    fee_tot = [report.fees.get(c.key, ZERO) for c in report.fee_columns]
    rows.append([
        "", "", "", "", report.count, report.gross,
        *fee_tot, report.net, "grand_total",
    ])
    return rows


def _fmt_csv(v):
    if v is None or v == "":
        return ""
    if isinstance(v, Decimal):
        return f"{v:.2f}".replace(".", ",")
    return str(v)


class OrderDetailCSVRenderer:
    def __init__(self, report):
        self.report = report

    def render(self) -> bytes:
        out = io.StringIO()
        out.write(BOM)
        w = csv.writer(out, delimiter=";", lineterminator="\r\n")
        w.writerow(column_headers(self.report))
        for row in flatten(self.report):
            w.writerow([_fmt_csv(v) for v in row])
        return out.getvalue().encode("utf-8")


EUR_FMT = "# ##0.00 €"
ACCENT = "4F46E5"
HEAD_FILL = PatternFill("solid", fgColor="EEF0FB")
TOTAL_FILL = PatternFill("solid", fgColor="EEF0FB")
THIN = Side(style="thin", color="E5E7EB")


class OrderDetailExcelRenderer:
    def __init__(self, report):
        self.report = report

    def render(self) -> bytes:
        wb = Workbook()
        ws = wb.active
        ws.title = str(_("Commandes"))
        headers = column_headers(self.report)
        kind_idx = len(headers) - 1  # drop technical "kind"
        ws.append(headers[:kind_idx])
        for c in range(1, kind_idx + 1):
            cell = ws.cell(row=1, column=c)
            cell.font = Font(bold=True, color=ACCENT, size=9)
            cell.fill = HEAD_FILL
            cell.border = Border(bottom=Side(style="medium", color=ACCENT))
        ws.freeze_panes = "A2"
        # amount columns: gross(6), fees.., net(last data col)
        amount_cols = list(range(6, kind_idx))
        for row in flatten(self.report):
            kind = row[-1]
            ws.append(list(row[:kind_idx]))
            r = ws.max_row
            for c in range(1, kind_idx + 1):
                cell = ws.cell(row=r, column=c)
                cell.border = Border(bottom=THIN)
                if c in amount_cols and isinstance(
                    cell.value, (int, float, Decimal)
                ):
                    cell.number_format = EUR_FMT
                    cell.alignment = Alignment(horizontal="right")
                elif c == 4:  # count
                    cell.alignment = Alignment(horizontal="right")
                if kind == "grand_total":
                    cell.font = Font(bold=True, color=ACCENT)
                    cell.fill = TOTAL_FILL
        # autosize
        for c in range(1, kind_idx + 1):
            width = 10
            for row in ws.iter_rows(min_col=c, max_col=c):
                v = row[0].value
                if v is not None:
                    width = max(width, min(len(str(v)) + 2, 50))
            ws.column_dimensions[
                ws.cell(row=1, column=c).column_letter
            ].width = width
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()
