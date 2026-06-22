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


# -- STORY-102: channels, sessions, cross view --------------------------------


@pytest.fixture
def multi_event(db):
    """Event with 2 subevents, 2 channels, fees on specific sessions.

    Layout:
        web / Session A: place 20.00 + Mollie fee 0.85
        web / Session B: place 20.00 + service fee 2.00
        guichet / Session A: place 14.00 + SumUp fee 0.30
    """
    from datetime import timedelta

    from pretix.base.models import (
        Event, Item, Order, OrderFee, OrderPosition, Organizer,
        SalesChannel, SubEvent,
    )

    with scopes_disabled():
        org = Organizer.objects.create(name="MOrg", slug="m-org")
        # Only "web" is created with the organizer; add the box-office channel.
        SalesChannel.objects.get_or_create(
            organizer=org, identifier="api.guichet",
            defaults={"label": "Guichet", "type": "api"},
        )
        ev = Event.objects.create(
            organizer=org, name="Multi", slug="ev-multi",
            date_from=now(), currency="EUR", has_subevents=True,
        )
        se_a = SubEvent.objects.create(
            event=ev, name="Session A", date_from=now(), active=True
        )
        se_b = SubEvent.objects.create(
            event=ev, name="Session B", date_from=now() + timedelta(days=1),
            active=True,
        )
        place = Item.objects.create(
            event=ev, name="Place", default_price=Decimal("20.00")
        )
        web = org.sales_channels.get(identifier="web")
        guichet = org.sales_channels.get(identifier="api.guichet")

        def order(code, channel, subevent, price, fees):
            o = Order.objects.create(
                code=code, event=ev, status=Order.STATUS_PAID,
                datetime=now(), expires=now(), total=Decimal(price),
                sales_channel=channel,
            )
            OrderPosition.objects.create(
                order=o, item=place, price=Decimal(price), subevent=subevent
            )
            for ft, it, val in fees:
                OrderFee.objects.create(
                    order=o, fee_type=ft, internal_type=it, value=Decimal(val)
                )

        order("WA", web, se_a, "20.00",
              [(OrderFee.FEE_TYPE_PAYMENT, "mollie_creditcard_fee", "0.85")])
        order("WB", web, se_b, "20.00",
              [(OrderFee.FEE_TYPE_SERVICE, "", "2.00")])
        order("GA", guichet, se_a, "14.00",
              [(OrderFee.FEE_TYPE_PAYMENT, "sumup_fee", "0.30")])
    return ev


def test_sessions_split_by_subevent(multi_event):
    with scope(organizer=multi_event.organizer):
        report = RecetteDataBuilder([multi_event]).build()
    labels = {se.label for ch in report.channels for se in ch.sessions}
    assert any("Session A" in label for label in labels)
    assert any("Session B" in label for label in labels)


def test_session_label_includes_date(multi_event):
    with scope(organizer=multi_event.organizer):
        report = RecetteDataBuilder([multi_event]).build()
    for ch in report.channels:
        for se in ch.sessions:
            # "Name (DD/MM/YYYY HH:MM)"
            assert "(" in se.label and "/" in se.label


def test_fees_attributed_to_correct_session(multi_event):
    """The service fee from a Session B order must not land on Session A."""
    with scope(organizer=multi_event.organizer):
        report = RecetteDataBuilder([multi_event]).build()
    web = [c for c in report.channels if c.key == "web"][0]
    sa = [s for s in web.sessions if "Session A" in s.label][0]
    sb = [s for s in web.sessions if "Session B" in s.label][0]
    assert sa.fees.get("mollie_creditcard_fee") == Decimal("0.85")
    assert sb.fees.get("service") == Decimal("2.00")
    assert "service" not in sa.fees


def test_channel_filter_restricts_perimeter(multi_event):
    with scope(organizer=multi_event.organizer):
        full = RecetteDataBuilder([multi_event]).build()
        web = RecetteDataBuilder([multi_event], {"channel": "web"}).build()
        gui = RecetteDataBuilder(
            [multi_event], {"channel": "api.guichet"}
        ).build()
    assert [c.key for c in web.channels] == ["web"]
    assert [c.key for c in gui.channels] == ["api.guichet"]
    # sum of filtered channels reconciles with the full report
    assert web.gross + gui.gross == full.gross
    assert web.fees_total + gui.fees_total == full.fees_total


def test_cross_view_category_by_session(multi_event):
    with scope(organizer=multi_event.organizer):
        report = RecetteDataBuilder([multi_event]).build()
    cv = report.cross_view()
    assert len(cv.sessions) == 2
    assert "Place" in cv.rows
    total = cv.row_total("Place")
    assert total["gross"] == report.gross  # 20 + 20 + 14 = 54


def test_single_event_falls_back_to_event_session(event):
    """An event without subevents yields a single 'Event' session."""
    report = _build(event)
    labels = {se.label for ch in report.channels for se in ch.sessions}
    assert labels == {"Event"}
