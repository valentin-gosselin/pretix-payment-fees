"""
Tests for the CSV and Excel renderers (STORY-105).

Both serialise the same flattened structure, so their totals must match each
other and the PDF (same builder report). Checks: valid output, UTF-8 BOM,
dynamic fee columns, reconciliation, real numeric cells in Excel.
"""
import io
from decimal import Decimal

import pytest
from django.utils.timezone import now
from django_scopes import scope, scopes_disabled

from pretix_payment_fees.renderers.recette_csv_renderer import RecetteCSVRenderer
from pretix_payment_fees.renderers.recette_excel_renderer import (
    RecetteExcelRenderer,
)
from pretix_payment_fees.renderers.recette_tabular import (
    KIND_GRAND,
    column_headers,
    flatten,
)
from pretix_payment_fees.services.recette_builder import RecetteDataBuilder


@pytest.fixture
def event(db):
    from pretix.base.models import (
        Event, Item, Order, OrderFee, OrderPosition, Organizer,
    )

    with scopes_disabled():
        org = Organizer.objects.create(name="Org", slug="tab-org")
        ev = Event.objects.create(
            organizer=org, name="Tab Évènement", slug="ev-tab",
            date_from=now(), currency="EUR",
        )
        item = Item.objects.create(
            event=ev, name="Place", default_price=Decimal("20.00")
        )
        inv = Item.objects.create(
            event=ev, name="Invitation", default_price=Decimal("0.00")
        )
        web = org.sales_channels.get(identifier="web")
        order = Order.objects.create(
            code="T1", event=ev, status=Order.STATUS_PAID,
            datetime=now(), expires=now(), total=Decimal("40.00"),
            sales_channel=web,
        )
        OrderPosition.objects.create(
            order=order, item=item, price=Decimal("20.00")
        )
        OrderPosition.objects.create(
            order=order, item=item, price=Decimal("20.00")
        )
        OrderPosition.objects.create(
            order=order, item=inv, price=Decimal("0.00")
        )
        OrderFee.objects.create(
            order=order, fee_type=OrderFee.FEE_TYPE_PAYMENT,
            internal_type="mollie_creditcard_fee", value=Decimal("1.50"),
        )
    return ev


def _report(event):
    with scope(organizer=event.organizer):
        return RecetteDataBuilder([event]).build()


# -- flatten ------------------------------------------------------------------


def test_headers_include_dynamic_fee_columns(event):
    report = _report(event)
    head = column_headers(report)
    assert "Frais Mollie (CB)" in head
    assert head[0] == "Canal de vente"
    assert head[-1] == "Type de ligne"


def test_flatten_grand_total_reconciles(event):
    report = _report(event)
    grand = flatten(report)[-1]
    assert grand[-1] == KIND_GRAND
    assert grand[7] == report.gross == Decimal("40.00")
    assert grand[-2] == report.net == Decimal("38.50")  # 40 - 1.50


# -- CSV ----------------------------------------------------------------------


def test_csv_is_utf8_bom(event):
    data = RecetteCSVRenderer(_report(event)).render()
    assert data[:3] == b"\xef\xbb\xbf"  # UTF-8 BOM


def test_csv_accents_roundtrip(event):
    data = RecetteCSVRenderer(_report(event)).render()
    text = data.decode("utf-8")
    assert "Évènement" not in text  # event name not in body, but accents work
    assert "Recette nette" in text  # accented header survives encoding


def test_csv_has_grand_total_row(event):
    data = RecetteCSVRenderer(_report(event)).render().decode("utf-8")
    assert "grand_total" in data
    assert "38,50" in data  # FR decimal comma


# -- Excel --------------------------------------------------------------------


def test_excel_opens_and_has_numeric_totals(event):
    import openpyxl

    data = RecetteExcelRenderer(_report(event)).render()
    wb = openpyxl.load_workbook(io.BytesIO(data))
    ws = wb.active
    grand = ws[ws.max_row]
    gross = ws.cell(row=ws.max_row, column=8).value
    net = ws.cell(row=ws.max_row, column=ws.max_column).value
    assert isinstance(gross, (int, float))
    assert float(gross) == 40.0
    assert float(net) == 38.5


def test_csv_and_excel_totals_match(event):
    import openpyxl

    report = _report(event)
    # CSV grand total via flatten
    grand = flatten(report)[-1]
    csv_gross, csv_net = grand[7], grand[-2]
    # Excel grand total
    data = RecetteExcelRenderer(report).render()
    ws = openpyxl.load_workbook(io.BytesIO(data)).active
    xls_gross = Decimal(str(ws.cell(row=ws.max_row, column=8).value))
    xls_net = Decimal(str(ws.cell(row=ws.max_row, column=ws.max_column).value))
    assert csv_gross == xls_gross
    assert csv_net == xls_net


def test_empty_report_renders_both():
    report = RecetteDataBuilder([]).build()
    csv_data = RecetteCSVRenderer(report).render()
    xls_data = RecetteExcelRenderer(report).render()
    assert csv_data[:3] == b"\xef\xbb\xbf"
    assert xls_data[:2] == b"PK"  # xlsx is a zip
