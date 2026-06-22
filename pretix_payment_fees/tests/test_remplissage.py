"""
Tests for the "Remplissage de salle" builder and exporter (STORY-202).

Checks category counts, quota fill rates, the no-monetary-value guarantee, the
no-quota fallback, and the 3 export formats.
"""
import io
from decimal import Decimal

import pytest
from django.utils import translation
from django.utils.timezone import now
from django_scopes import scope, scopes_disabled

from pretix_payment_fees.exporters.remplissage_salle import (
    RemplissageSalleExporter,
)
from pretix_payment_fees.services.remplissage_builder import RemplissageBuilder


@pytest.fixture
def event(db):
    from pretix.base.models import (
        Event, Item, Order, OrderPosition, Organizer, Quota,
    )

    with scopes_disabled():
        org = Organizer.objects.create(name="Org", slug="rs-org")
        ev = Event.objects.create(
            organizer=org, name="RS Event", slug="ev-rs",
            date_from=now(), currency="EUR", plugins="pretix_payment_fees",
        )
        plein = Item.objects.create(
            event=ev, name="Plein", default_price=Decimal("20.00")
        )
        invit = Item.objects.create(
            event=ev, name="Invitation", default_price=Decimal("0.00")
        )
        web = org.sales_channels.get(identifier="web")
        # quota "Salle" size 10 covering the paying item
        q = Quota.objects.create(event=ev, name="Salle", size=10)
        q.items.add(plein)

        o = Order.objects.create(
            code="O1", event=ev, status=Order.STATUS_PAID,
            datetime=now(), expires=now(), total=Decimal("40.00"),
            sales_channel=web,
        )
        # 2 paying + 1 invitation
        OrderPosition.objects.create(order=o, item=plein, price=Decimal("20"))
        OrderPosition.objects.create(order=o, item=plein, price=Decimal("20"))
        OrderPosition.objects.create(order=o, item=invit, price=Decimal("0"))
    return ev


def _build(event):
    with scope(organizer=event.organizer):
        return RemplissageBuilder([event]).build()


def test_category_counts(event):
    report = _build(event)
    cats = {c.name: c for c in report.categories}
    assert cats["Plein"].paid == 2 and cats["Plein"].free == 0
    assert cats["Invitation"].free == 1
    assert report.total_places == 3
    assert report.total_paid == 2 and report.total_free == 1


def test_quota_fill_rate(event):
    report = _build(event)
    salle = next(q for q in report.quotas if q.name == "Salle")
    assert salle.size == 10
    assert salle.sold == 2          # 2 paying positions of "Plein"
    assert salle.rate == Decimal("20.0")
    assert "20,0 %" == salle.rate_display


def test_no_quota_size_no_rate():
    """A quota without size (unlimited) yields no rate."""
    from pretix_payment_fees.services.remplissage_builder import QuotaFill

    q = QuotaFill(name="Libre", size=None, sold=5)
    assert q.rate is None
    assert q.rate_display == ""


def test_export_pdf_has_no_money(event):
    with scope(organizer=event.organizer), translation.override("fr"):
        _f, _c, pdf = RemplissageSalleExporter(
            event, event.organizer
        ).render({"_format": "pdf"})
    assert pdf[:4] == b"%PDF"
    assert "€".encode("utf-8") not in pdf


def test_export_csv_has_no_money(event):
    with scope(organizer=event.organizer), translation.override("fr"):
        _f, _c, csv = RemplissageSalleExporter(
            event, event.organizer
        ).render({"_format": "csv"})
    text = csv.decode("utf-8")
    assert "€" not in text
    assert "Remplissage" in text  # quota section present


def test_export_xlsx(event):
    with scope(organizer=event.organizer):
        _f, _c, data = RemplissageSalleExporter(
            event, event.organizer
        ).render({"_format": "xlsx"})
    assert data[:2] == b"PK"


def test_registered(event):
    from pretix.base.signals import register_data_exporters

    with scope(organizer=event.organizer):
        ids = [getattr(r, "identifier", None)
               for _r, r in register_data_exporters.send(event) if r]
    assert "remplissage_salle" in ids


def test_empty_event():
    report = RemplissageBuilder([]).build()
    assert report.total_places == 0
    assert report.quotas == []
