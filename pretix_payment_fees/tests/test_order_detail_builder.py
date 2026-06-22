"""
Tests for OrderDetailBuilder (STORY-200).

Focus: one row per order, category breakdown, fee reconciliation, and the GDPR
guarantee that no personal data is exposed.
"""
from decimal import Decimal

import pytest
from django.utils.timezone import now
from django_scopes import scope, scopes_disabled

from pretix_payment_fees.services.order_detail_builder import (
    OrderDetailBuilder,
    OrderDetailRow,
)


@pytest.fixture
def event(db):
    from pretix.base.models import (
        Event, Item, Order, OrderFee, OrderPosition, Organizer,
    )

    with scopes_disabled():
        org = Organizer.objects.create(name="Org", slug="od-org")
        ev = Event.objects.create(
            organizer=org, name="OD Event", slug="ev-od",
            date_from=now(), currency="EUR",
        )
        plein = Item.objects.create(
            event=ev, name="Tarif plein", default_price=Decimal("20.00")
        )
        reduit = Item.objects.create(
            event=ev, name="Réduit", default_price=Decimal("14.00")
        )
        web = org.sales_channels.get(identifier="web")

        # order 1: 2 plein + 1 réduit + a Mollie fee, with an email (must NOT
        # surface in the export)
        o1 = Order.objects.create(
            code="AAAAA", event=ev, status=Order.STATUS_PAID,
            datetime=now(), expires=now(), total=Decimal("54.00"),
            sales_channel=web, email="buyer@example.com",
        )
        OrderPosition.objects.create(order=o1, item=plein, price=Decimal("20"))
        OrderPosition.objects.create(order=o1, item=plein, price=Decimal("20"))
        OrderPosition.objects.create(order=o1, item=reduit, price=Decimal("14"))
        OrderFee.objects.create(
            order=o1, fee_type=OrderFee.FEE_TYPE_PAYMENT,
            internal_type="mollie_creditcard_fee", value=Decimal("1.50"),
        )
        # order 2: 1 plein, no fee (paid offline)
        o2 = Order.objects.create(
            code="BBBBB", event=ev, status=Order.STATUS_PAID,
            datetime=now(), expires=now(), total=Decimal("20.00"),
            sales_channel=web, email="other@example.com",
        )
        OrderPosition.objects.create(order=o2, item=plein, price=Decimal("20"))
        # canceled order: must be excluded
        oc = Order.objects.create(
            code="CCCCC", event=ev, status=Order.STATUS_CANCELED,
            datetime=now(), expires=now(), total=Decimal("20.00"),
            sales_channel=web,
        )
        OrderPosition.objects.create(order=oc, item=plein, price=Decimal("20"))
    return ev


def _build(event):
    with scope(organizer=event.organizer):
        return OrderDetailBuilder([event]).build()


def test_one_row_per_order(event):
    report = _build(event)
    assert report.order_count == 2  # canceled excluded
    codes = {r.code for r in report.rows}
    assert codes == {"AAAAA", "BBBBB"}


def test_counts_and_gross(event):
    report = _build(event)
    assert report.count == 4  # 3 + 1
    assert report.gross == Decimal("74.00")  # 54 + 20


def test_product_lines(event):
    """A multi-product order yields one product line per (item, price)."""
    report = _build(event)
    row = next(r for r in report.rows if r.code == "AAAAA")
    products = {ln.product: ln for ln in row.lines}
    assert products["Tarif plein"].count == 2
    assert products["Tarif plein"].gross == Decimal("40.00")
    assert products["Réduit"].count == 1
    assert products["Réduit"].gross == Decimal("14.00")
    assert row.count == 3 and row.gross == Decimal("54.00")


def test_fee_allocated_per_product_line(event):
    """The order fee is split over its product lines, pro rata of gross."""
    report = _build(event)
    row = next(r for r in report.rows if r.code == "AAAAA")
    line_sum = sum((ln.fees_total for ln in row.lines), Decimal("0.00"))
    assert line_sum == Decimal("1.50")  # = the order's Mollie fee
    # the larger line (40) gets a bigger share than the smaller (14)
    plein = next(ln for ln in row.lines if ln.product == "Tarif plein")
    reduit = next(ln for ln in row.lines if ln.product == "Réduit")
    assert plein.fees_total > reduit.fees_total


def test_fees_per_order(event):
    report = _build(event)
    a = next(r for r in report.rows if r.code == "AAAAA")
    b = next(r for r in report.rows if r.code == "BBBBB")
    assert a.fees.get("mollie_creditcard_fee") == Decimal("1.50")
    assert b.fees == {}  # offline order, no fee
    assert a.net == Decimal("52.50")  # 54 - 1.50


def test_fee_reconciliation(event):
    report = _build(event)
    assert report.fees_total == Decimal("1.50")
    assert report.fees_reconciled
    rec = report.fee_reconciliation()
    assert rec["mollie_creditcard_fee"]["ok"] is True


def test_no_personal_data_in_rows(event):
    """GDPR: no email/name field on the row dataclass nor in its values."""
    report = _build(event)
    fields = set(OrderDetailRow.__dataclass_fields__)
    assert "email" not in fields
    assert "name" not in fields and "buyer" not in fields
    # and the buyer email never appears in any string value
    for row in report.rows:
        blob = " ".join([row.code, row.channel]
                        + [ln.product for ln in row.lines])
        assert "@example.com" not in blob


def test_fee_columns_declared(event):
    report = _build(event)
    keys = [c.key for c in report.fee_columns]
    assert keys == ["mollie_creditcard_fee"]


def test_empty_events():
    report = OrderDetailBuilder([]).build()
    assert report.order_count == 0
    assert report.gross == Decimal("0.00")


def test_channel_filter(event):
    with scope(organizer=event.organizer):
        web = OrderDetailBuilder([event], {"channel": "web"}).build()
        none = OrderDetailBuilder(
            [event], {"channel": "api.guichet"}
        ).build()
    assert web.order_count == 2
    assert none.order_count == 0  # no orders on that channel
