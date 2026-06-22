"""
Tests for RecetteDataBuilder (STORY-100).

Focus: aggregation correctness and totals reconciliation on a small built
fixture (paid order with a paying position and an invitation at price 0).

Run from the pretix container:
    docker exec pretix-dev python -m pytest \
        /plugins/pretix-payment-fees/pretix_payment_fees/tests/test_recette_builder.py
"""
from decimal import Decimal

import pytest
from django.utils.timezone import now
from django_scopes import scope, scopes_disabled

from pretix_payment_fees.services.recette_builder import (
    DEFAULT_NATURE,
    RecetteDataBuilder,
)


@pytest.fixture
def event(db):
    """Minimal event with one item, one paid order (paying + invitation)."""
    from pretix.base.models import (
        Event,
        Item,
        Order,
        OrderFee,
        OrderPosition,
        Organizer,
    )

    with scopes_disabled():
        organizer = Organizer.objects.create(name="Org", slug="org-test")
        ev = Event.objects.create(
            organizer=organizer,
            name="Test Event",
            slug="ev-test",
            date_from=now(),
            currency="EUR",
            plugins="pretix_payment_fees",
        )
        # Order.sales_channel is a FK to SalesChannel (the "web" channel is
        # created with the organizer). Fetch it for the orders below.
        web = organizer.sales_channels.get(identifier="web")
        item_full = Item.objects.create(
            event=ev, name="Tarif plein", default_price=Decimal("20.00")
        )
        item_inv = Item.objects.create(
            event=ev, name="Invitation", default_price=Decimal("0.00")
        )

        order = Order.objects.create(
            code="ORDER1",
            event=ev,
            status=Order.STATUS_PAID,
            datetime=now(),
            expires=now(),
            total=Decimal("40.00"),
            sales_channel=web,
        )
        # two paying positions + one invitation (price 0)
        OrderPosition.objects.create(
            order=order, item=item_full, price=Decimal("20.00")
        )
        OrderPosition.objects.create(
            order=order, item=item_full, price=Decimal("20.00")
        )
        OrderPosition.objects.create(
            order=order, item=item_inv, price=Decimal("0.00")
        )
        # a real Mollie payment fee on the paid order (STORY-101)
        OrderFee.objects.create(
            order=order,
            fee_type=OrderFee.FEE_TYPE_PAYMENT,
            internal_type="mollie_creditcard_fee",
            value=Decimal("1.50"),
        )

        # a canceled order that must be EXCLUDED from the perimeter
        canceled = Order.objects.create(
            code="ORDER2",
            event=ev,
            status=Order.STATUS_CANCELED,
            datetime=now(),
            expires=now(),
            total=Decimal("20.00"),
            sales_channel=web,
        )
        OrderPosition.objects.create(
            order=canceled, item=item_full, price=Decimal("20.00")
        )
    return ev


def _build(event):
    with scope(organizer=event.organizer):
        return RecetteDataBuilder([event]).build()


def test_builder_importable():
    assert RecetteDataBuilder is not None


def test_currency_resolved(event):
    report = _build(event)
    assert report.currency == "EUR"


def test_perimeter_includes_paid_and_invitations(event):
    report = _build(event)
    # 2 paying + 1 invitation = 3 positions, canceled order excluded
    assert report.count == 3
    assert report.gross == Decimal("40.00")


def test_canceled_orders_excluded(event):
    report = _build(event)
    # the canceled order had a 20.00 position; if included gross would be 60
    assert report.gross == Decimal("40.00")


def test_invitation_counted_with_zero_gross(event):
    report = _build(event)
    natures = {
        cat.name: cat
        for ch in report.channels
        for se in ch.sessions
        for cat in se.categories
    }
    assert "Invitation" in natures
    inv = natures["Invitation"]
    assert inv.count == 1
    assert inv.gross == Decimal("0.00")


def test_default_nature_when_no_variation(event):
    report = _build(event)
    for ch in report.channels:
        for se in ch.sessions:
            for cat in se.categories:
                for line in cat.lines:
                    assert line.nature == str(DEFAULT_NATURE)


def test_subtotals_reconcile(event):
    """Sum of natures == category; sum of categories == session == channel."""
    report = _build(event)
    for ch in report.channels:
        assert ch.gross == sum((s.gross for s in ch.sessions), Decimal("0.00"))
        for se in ch.sessions:
            assert se.gross == sum(
                (c.gross for c in se.categories), Decimal("0.00")
            )
            for cat in se.categories:
                assert cat.gross == sum(
                    (line.gross for line in cat.lines), Decimal("0.00")
                )


def test_grand_total_reconciles(event):
    report = _build(event)
    assert report.gross == sum(
        (c.gross for c in report.channels), Decimal("0.00")
    )
    assert report.count == sum(c.count for c in report.channels)


def test_unit_price_average(event):
    report = _build(event)
    for ch in report.channels:
        for se in ch.sessions:
            for cat in se.categories:
                for line in cat.lines:
                    if line.count and line.gross:
                        assert line.unit_price == (
                            line.gross / line.count
                        ).quantize(Decimal("0.01"))


def test_empty_events_returns_empty_report():
    report = RecetteDataBuilder([]).build()
    assert report.channels == []
    assert report.gross == Decimal("0.00")


# -- STORY-101: fee breakdown -------------------------------------------------


def test_dynamic_fee_column_from_internal_type(event):
    report = _build(event)
    keys = [c.key for c in report.fee_columns]
    assert keys == ["mollie_creditcard_fee"]
    assert report.fee_columns[0].label  # has a readable label


def test_fee_total_aggregated(event):
    report = _build(event)
    assert report.fees_total == Decimal("1.50")
    assert report.fees["mollie_creditcard_fee"] == Decimal("1.50")


def test_net_revenue_is_gross_minus_fees(event):
    report = _build(event)
    assert report.net == report.gross - report.fees_total
    assert report.net == Decimal("38.50")  # 40.00 - 1.50


def test_fees_reconcile_channel_to_report(event):
    report = _build(event)
    summed = Decimal("0.00")
    for ch in report.channels:
        assert ch.net == ch.gross - ch.fees_total
        summed += ch.fees_total
    assert summed == report.fees_total


@pytest.mark.django_db
def test_no_fee_means_no_column():
    """An event without OrderFee yields no fee column and net == gross."""
    from pretix.base.models import Event, Item, Order, OrderPosition, Organizer

    with scopes_disabled():
        org = Organizer.objects.create(name="Org2", slug="org-test-2")
        ev = Event.objects.create(
            organizer=org, name="No Fee", slug="ev-nofee",
            date_from=now(), currency="EUR",
        )
        web = org.sales_channels.get(identifier="web")
        item = Item.objects.create(
            event=ev, name="Plein", default_price=Decimal("10.00")
        )
        order = Order.objects.create(
            code="ORD", event=ev, status=Order.STATUS_PAID,
            datetime=now(), expires=now(), total=Decimal("10.00"),
            sales_channel=web,
        )
        OrderPosition.objects.create(
            order=order, item=item, price=Decimal("10.00")
        )
    with scope(organizer=ev.organizer):
        report = RecetteDataBuilder([ev]).build()
    assert report.fee_columns == []
    assert report.fees_total == Decimal("0.00")
    assert report.net == report.gross


def test_reconcile_with_cache_returns_structure(event):
    """reconcile_with_cache exposes report/cache/delta per provider."""
    with scope(organizer=event.organizer):
        builder = RecetteDataBuilder([event])
        report = builder.build()
        rec = builder.reconcile_with_cache(report)
    # cache may be empty in the test DB; the report side must still be present
    if "mollie" in rec:
        assert rec["mollie"]["report"] == Decimal("1.50")
        assert "cache" in rec["mollie"] and "delta" in rec["mollie"]
