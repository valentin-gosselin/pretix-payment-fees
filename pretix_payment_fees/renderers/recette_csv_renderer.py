"""
CSV renderer for the "Recette Manifestation" export (STORY-105).

Serialises the builder report flattened by recette_tabular.flatten(). Totals are
identical to the PDF and Excel outputs (same source structure).

Encoding: UTF-8 with BOM so Excel (FR locale) opens accents correctly.
Separator: semicolon (Excel FR default), decimal comma in amounts.
"""
import csv
import io
from decimal import Decimal

from .recette_tabular import column_headers, flatten

BOM = "﻿"


def _fmt(value):
    """Format a cell for CSV: FR decimal comma for amounts, plain for the rest."""
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return f"{value:.2f}".replace(".", ",")
    return str(value)


class RecetteCSVRenderer:
    """Render a RecetteReport to CSV bytes (UTF-8 BOM, semicolon-separated)."""

    def __init__(self, report):
        self.report = report

    def render(self) -> bytes:
        out = io.StringIO()
        out.write(BOM)
        writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
        writer.writerow(column_headers(self.report))
        for row in flatten(self.report):
            writer.writerow([_fmt(v) for v in row])
        return out.getvalue().encode("utf-8")
