"""
Tests for RecettePDFRenderer (STORY-104).

The renderer must produce a valid PDF from a builder report without error,
embed OpenSans, and not crash on edge cases (no fees, single channel).
"""
from decimal import Decimal

import pytest
from django.utils.timezone import now
from django_scopes import scope, scopes_disabled

from pretix_payment_fees.renderers.recette_pdf_renderer import (
    RecettePDFRenderer,
    euro,
)
from pretix_payment_fees.services.recette_builder import RecetteDataBuilder


@pytest.fixture
def event(db):
    from pretix.base.models import (
        Event, Item, Order, OrderFee, OrderPosition, Organizer,
    )

    with scopes_disabled():
        org = Organizer.objects.create(name="Org", slug="pdf-org")
        ev = Event.objects.create(
            organizer=org, name="PDF Event", slug="ev-pdf",
            date_from=now(), currency="EUR",
        )
        item = Item.objects.create(
            event=ev, name="Place", default_price=Decimal("20.00")
        )
        web = org.sales_channels.get(identifier="web")
        order = Order.objects.create(
            code="P1", event=ev, status=Order.STATUS_PAID,
            datetime=now(), expires=now(), total=Decimal("20.00"),
            sales_channel=web,
        )
        OrderPosition.objects.create(
            order=order, item=item, price=Decimal("20.00")
        )
        OrderFee.objects.create(
            order=order, fee_type=OrderFee.FEE_TYPE_PAYMENT,
            internal_type="mollie_creditcard_fee", value=Decimal("0.50"),
        )
    return ev


def _render(event, meta=None):
    with scope(organizer=event.organizer):
        report = RecetteDataBuilder([event]).build()
        return RecettePDFRenderer(report, meta).render()


def test_euro_format():
    assert euro(Decimal("1234.5")) == "1 234,50 €"
    assert euro(Decimal("0")) == "0,00 €"
    assert euro(None) == ""


def test_renders_valid_pdf(event):
    pdf = _render(event, {"organizer": "Org", "event": "PDF Event"})
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 1000


def test_pdf_embeds_opensans(event):
    pdf = _render(event)
    # OpenSans is embedded -> its name appears in the font descriptors
    assert b"OpenSans" in pdf


@pytest.mark.django_db
def test_no_fee_event_renders():
    """An event without fees must still render (no fee columns)."""
    from pretix.base.models import Event, Item, Order, OrderPosition, Organizer

    with scopes_disabled():
        org = Organizer.objects.create(name="NF", slug="pdf-nofee")
        ev = Event.objects.create(
            organizer=org, name="NoFee", slug="ev-pdf-nofee",
            date_from=now(), currency="EUR",
        )
        item = Item.objects.create(
            event=ev, name="Place", default_price=Decimal("10.00")
        )
        web = org.sales_channels.get(identifier="web")
        o = Order.objects.create(
            code="N1", event=ev, status=Order.STATUS_PAID,
            datetime=now(), expires=now(), total=Decimal("10.00"),
            sales_channel=web,
        )
        OrderPosition.objects.create(
            order=o, item=item, price=Decimal("10.00")
        )
    with scope(organizer=ev.organizer):
        report = RecetteDataBuilder([ev]).build()
        pdf = RecettePDFRenderer(report).render()
    assert pdf[:4] == b"%PDF"


def test_empty_report_renders():
    """An empty report (no channels) still produces a valid PDF."""
    report = RecetteDataBuilder([]).build()
    pdf = RecettePDFRenderer(report).render()
    assert pdf[:4] == b"%PDF"
