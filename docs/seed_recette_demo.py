"""
Seed a complete demo event to exercise the "Recette Manifestation" export.

Creates organizer "demo" event "recette-demo" with everything the export needs
to be exercised end to end:
    - 2 subevents (sessions)
    - 2 sales channels (web + api.guichet)
    - products WITH variations (category x nature) and a flat one
    - invitations (price 0)
    - real-shaped PSP fees: Mollie (web) AND SumUp (guichet)
    - a tax rule (VAT 2.10%)

Idempotent: deletes and recreates the event on each run.

Run inside the pretix container:
    cat docs/seed_recette_demo.py | docker exec -i pretix-dev \\
        python3 -m pretix shell --no-startup
"""
from decimal import Decimal

from django.utils.timezone import now, timedelta
from django_scopes import scopes_disabled

from pretix.base.models import (
    Event,
    Item,
    ItemVariation,
    Order,
    OrderFee,
    OrderPosition,
    Organizer,
    SubEvent,
    TaxRule,
)

ORG_SLUG = "demo"
EVENT_SLUG = "recette-demo"


def run():
    with scopes_disabled():
        org = Organizer.objects.get(slug=ORG_SLUG)
        if Event.objects.filter(organizer=org, slug=EVENT_SLUG).exists():
            print(f"Event {ORG_SLUG}/{EVENT_SLUG} already exists; delete it "
                  "first (SQL cascade) before re-seeding.")
            return

        ev = Event.objects.create(
            organizer=org,
            name="Recette Demo (multi-séances)",
            slug=EVENT_SLUG,
            date_from=now(),
            currency="EUR",
            has_subevents=True,
            plugins="pretix_payment_fees",
        )
        tax = TaxRule.objects.create(event=ev, name="TVA", rate=Decimal("2.10"))

        se1 = SubEvent.objects.create(
            event=ev, name="Séance A", date_from=now(), active=True,
            date_to=now() + timedelta(hours=2),
        )
        se2 = SubEvent.objects.create(
            event=ev, name="Séance B", date_from=now() + timedelta(days=1),
            active=True, date_to=now() + timedelta(days=1, hours=2),
        )

        # Product WITH variations: "Place" -> Plein / Réduit
        place = Item.objects.create(
            event=ev, name="Place", default_price=Decimal("20.00"),
            tax_rule=tax,
        )
        v_plein = ItemVariation.objects.create(
            item=place, value="Plein", default_price=Decimal("20.00")
        )
        v_reduit = ItemVariation.objects.create(
            item=place, value="Réduit", default_price=Decimal("14.00")
        )
        # Flat product: "Invitation" (price 0)
        invitation = Item.objects.create(
            event=ev, name="Invitation", default_price=Decimal("0.00"),
            tax_rule=tax,
        )

        web = org.sales_channels.get(identifier="web")
        guichet = org.sales_channels.get(identifier="api.guichet")

        def make_order(code, channel, subevent, lines, fees=None):
            total = sum(p for _, _, p in lines)
            order = Order.objects.create(
                code=code, event=ev, status=Order.STATUS_PAID,
                datetime=now(), expires=now(), total=total,
                sales_channel=channel,
            )
            for item, variation, price in lines:
                # tax_value for an inclusive rate: price * rate / (100 + rate)
                tax_value = (price * tax.rate / (Decimal("100") + tax.rate)) \
                    .quantize(Decimal("0.01"))
                OrderPosition.objects.create(
                    order=order, item=item, variation=variation,
                    price=price, subevent=subevent, tax_rule=tax,
                    tax_rate=tax.rate, tax_value=tax_value,
                )
            for fee_type, internal_type, value in (fees or []):
                OrderFee.objects.create(
                    order=order, fee_type=fee_type,
                    internal_type=internal_type, value=value,
                    tax_value=Decimal("0.00"), tax_rate=Decimal("0.00"),
                )
            return order

        # --- WEB, Séance A: paying places + Mollie fee
        make_order("WEBA1", web, se1,
                   [(place, v_plein, Decimal("20.00")),
                    (place, v_reduit, Decimal("14.00"))],
                   [(OrderFee.FEE_TYPE_PAYMENT, "mollie_creditcard_fee",
                     Decimal("0.85"))])
        make_order("WEBA2", web, se1,
                   [(place, v_plein, Decimal("20.00"))],
                   [(OrderFee.FEE_TYPE_PAYMENT, "mollie_creditcard_fee",
                     Decimal("0.50"))])
        # --- WEB, Séance B: paying + Mollie fee + a service fee
        make_order("WEBB1", web, se2,
                   [(place, v_plein, Decimal("20.00")),
                    (place, v_plein, Decimal("20.00"))],
                   [(OrderFee.FEE_TYPE_PAYMENT, "mollie_creditcard_fee",
                     Decimal("1.00")),
                    (OrderFee.FEE_TYPE_SERVICE, "", Decimal("2.00"))])
        # --- GUICHET, Séance A: paying + SumUp fee + invitation
        make_order("GUIA1", guichet, se1,
                   [(place, v_reduit, Decimal("14.00")),
                    (invitation, None, Decimal("0.00"))],
                   [(OrderFee.FEE_TYPE_PAYMENT, "sumup_fee", Decimal("0.30"))])
        # --- GUICHET, Séance B: invitation only (free)
        make_order("GUIB1", guichet, se2,
                   [(invitation, None, Decimal("0.00"))])

        print(f"OK: event {ORG_SLUG}/{EVENT_SLUG} created (id={ev.pk})")
        print("  subevents:", se1.pk, se2.pk)
        print("  channels: web, api.guichet")
        print("  fees: Mollie (web) + SumUp (guichet) + service (web B)")


run()
