"""
Tests for RecetteManifestationExporter (STORY-106).

Checks the exporter is registered, exposes the expected form, and renders all
three formats with the right content types. Reuses a multi-channel fixture.
"""
from decimal import Decimal

import pytest
from django.utils.timezone import now
from django_scopes import scope, scopes_disabled

from pretix_payment_fees.exporters.recette_manifestation import (
    RecetteManifestationExporter,
)


@pytest.fixture
def event(db):
    from pretix.base.models import (
        Event, Item, Order, OrderFee, OrderPosition, Organizer, SalesChannel,
    )

    with scopes_disabled():
        org = Organizer.objects.create(name="Org", slug="exp-org")
        SalesChannel.objects.get_or_create(
            organizer=org, identifier="api.guichet",
            defaults={"label": "Guichet", "type": "api"},
        )
        ev = Event.objects.create(
            organizer=org, name="Export Event", slug="ev-exp",
            date_from=now(), currency="EUR",
            plugins="pretix_payment_fees",
        )
        item = Item.objects.create(
            event=ev, name="Place", default_price=Decimal("20.00")
        )
        web = org.sales_channels.get(identifier="web")
        order = Order.objects.create(
            code="E1", event=ev, status=Order.STATUS_PAID,
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


def _exp(event):
    return RecetteManifestationExporter(event, event.organizer)


def test_registered_for_event(event):
    from pretix.base.signals import register_data_exporters

    with scope(organizer=event.organizer):
        ids = []
        for _recv, resp in register_data_exporters.send(event):
            if resp:
                ids.append(getattr(resp, "identifier", None))
    assert "recette_manifestation" in ids


def test_form_fields(event):
    with scope(organizer=event.organizer):
        fields = _exp(event).export_form_fields
    assert set(fields) == {"date_range", "channel", "status", "_format"}


def test_channel_choices_include_all_and_channels(event):
    with scope(organizer=event.organizer):
        choices = dict(_exp(event)._channel_choices())
    assert "" in choices  # "All channels"
    assert "web" in choices


def test_render_pdf(event):
    with scope(organizer=event.organizer):
        fn, ct, data = _exp(event).render({"_format": "pdf"})
    assert fn.endswith(".pdf")
    assert ct == "application/pdf"
    assert data[:4] == b"%PDF"


def test_render_csv(event):
    with scope(organizer=event.organizer):
        fn, ct, data = _exp(event).render({"_format": "csv"})
    assert fn.endswith(".csv")
    assert ct == "text/csv"
    assert data[:3] == b"\xef\xbb\xbf"


def test_render_xlsx(event):
    with scope(organizer=event.organizer):
        fn, ct, data = _exp(event).render({"_format": "xlsx"})
    assert fn.endswith(".xlsx")
    assert "spreadsheetml" in ct
    assert data[:2] == b"PK"


def test_channel_filter_applied(event):
    """Filtering on a channel restricts the report."""
    with scope(organizer=event.organizer):
        _fn, _ct, full = _exp(event).render({"_format": "csv"})
        _fn, _ct, web = _exp(event).render(
            {"_format": "csv", "channel": "web"}
        )
        _fn, _ct, gui = _exp(event).render(
            {"_format": "csv", "channel": "api.guichet"}
        )
    # the guichet has no orders -> its CSV has only header + grand total
    assert len(gui) < len(web)


def test_event_meta_from_real_event(event):
    with scope(organizer=event.organizer):
        meta = _exp(event)._event_meta()
    assert meta["event"] == "Export Event"
    assert meta["slug"] == "ev-exp"
    assert "date" in meta
