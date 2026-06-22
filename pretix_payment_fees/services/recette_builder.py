"""
RecetteDataBuilder: revenue aggregation service for the "Recette
Manifestation" accounting export.

This service turns Pretix orders into a neutral, render-agnostic data
structure so that the PDF and CSV/Excel renderers consume exactly the same
totals without duplicating business logic.

STORY-100 scope: base aggregation only.
    Sales channel -> Session (subevent) -> Category (Item) -> Nature (Variation)
    Measures: count, unit price, gross revenue, per-category subtotals, grand total.

Out of scope here (later stories):
    - Fee columns / net revenue (STORY-101)
    - Channel/session fine logic and cross view (STORY-102)
    - Ticketing block and VAT (STORY-103)
    - Any rendering (STORY-104, 105)

Design rules (frozen in STORY-000):
    - Pretix native vocabulary (Product, Gross, Count...).
    - The builder performs NO rendering: it knows nothing about PDF or CSV.
"""

from collections import OrderedDict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional

from django.db.models import Count, Sum
from django.utils.translation import gettext_lazy as _
from pretix.base.models import Order, OrderPosition

# Order statuses included in the report perimeter. Paid orders only; positions
# priced at 0 (invitations / free admissions) are kept (they have a count but
# zero gross). Canceled/expired orders are excluded. The status set is made
# overridable through form_data later (STORY-106).
DEFAULT_STATUSES = (Order.STATUS_PAID,)

# Displayed when an order position has no variation.
DEFAULT_NATURE = _("(default)")

ZERO = Decimal("0.00")


@dataclass
class RecetteLine:
    """One Category x Nature row (Item x Variation)."""

    category: str                       # Item name
    nature: str                         # Variation value, or DEFAULT_NATURE
    count: int = 0
    gross: Decimal = ZERO               # sum of position prices
    fees: dict = field(default_factory=dict)  # filled in STORY-101, empty here

    @property
    def unit_price(self) -> Decimal:
        """Average unit price for the row (gross / count), 0 if no count."""
        if not self.count:
            return ZERO
        return (self.gross / self.count).quantize(Decimal("0.01"))


@dataclass
class RecetteCategory:
    """A category group (one Item) with its nature rows and subtotals."""

    name: str
    lines: List[RecetteLine] = field(default_factory=list)

    @property
    def count(self) -> int:
        return sum(line.count for line in self.lines)

    @property
    def gross(self) -> Decimal:
        return sum((line.gross for line in self.lines), ZERO)

    @property
    def is_single_line(self) -> bool:
        """True when the category has a single nature (no detail/subtotal dup)."""
        return len(self.lines) == 1


@dataclass
class RecetteSession:
    """A session group (one subevent, or the event if none)."""

    key: str                            # stable key (subevent id or 'event')
    label: str                          # human label (subevent/event name+date)
    categories: List[RecetteCategory] = field(default_factory=list)

    @property
    def count(self) -> int:
        return sum(c.count for c in self.categories)

    @property
    def gross(self) -> Decimal:
        return sum((c.gross for c in self.categories), ZERO)


@dataclass
class RecetteChannel:
    """A sales-channel group."""

    key: str                            # sales channel identifier
    label: str                          # sales channel label
    sessions: List[RecetteSession] = field(default_factory=list)

    @property
    def count(self) -> int:
        return sum(s.count for s in self.sessions)

    @property
    def gross(self) -> Decimal:
        return sum((s.gross for s in self.sessions), ZERO)


@dataclass
class RecetteReport:
    """Top-level neutral structure returned by the builder."""

    currency: str
    channels: List[RecetteChannel] = field(default_factory=list)

    @property
    def count(self) -> int:
        return sum(c.count for c in self.channels)

    @property
    def gross(self) -> Decimal:
        return sum((c.gross for c in self.channels), ZERO)


class RecetteDataBuilder:
    """Aggregate Pretix orders into a neutral RecetteReport.

    Usage:
        report = RecetteDataBuilder(events, form_data).build()

    `events` is a queryset/iterable of pretix Event objects (single or multi
    event export). `form_data` is the export form payload (optional here;
    status filtering becomes configurable in STORY-106).
    """

    def __init__(self, events, form_data: Optional[dict] = None):
        self.events = events
        self.form_data = form_data or {}
        self.statuses = self.form_data.get("statuses") or DEFAULT_STATUSES

    # -- public API ---------------------------------------------------------

    def build(self) -> RecetteReport:
        event_ids = [e.pk for e in self.events]
        currency = self._resolve_currency()
        report = RecetteReport(currency=currency)
        if not event_ids:
            return report

        rows = self._aggregate(event_ids)
        self._fill_report(report, rows)
        return report

    # -- internals ----------------------------------------------------------

    def _resolve_currency(self) -> str:
        currencies = {getattr(e, "currency", None) for e in self.events}
        currencies.discard(None)
        if len(currencies) == 1:
            return currencies.pop()
        # Multi-currency: keep a marker; per-currency split handled later.
        return "" if not currencies else sorted(currencies)[0]

    def _aggregate(self, event_ids):
        """Single aggregated ORM query, grouped by the full hierarchy.

        Returns an iterable of dict rows with keys:
            sales_channel, subevent, subevent_name, item, item_name,
            variation, variation_value, count, gross
        No per-order Python loop: everything is computed by the database.
        """
        qs = (
            OrderPosition.objects.filter(
                order__event_id__in=event_ids,
                order__status__in=self.statuses,
            )
            .values(
                "order__sales_channel__identifier",
                "order__sales_channel__label",
                "subevent",
                "subevent__name",
                "item",
                "item__name",
                "variation",
                "variation__value",
            )
            .annotate(count=Count("id"), gross=Sum("price"))
            .order_by(
                "order__sales_channel__label",
                "subevent",
                "item__name",
                "variation__value",
            )
        )
        return qs

    def _fill_report(self, report: RecetteReport, rows):
        # Nested ordered maps keep first-seen ordering stable for renderers.
        channels = OrderedDict()

        for row in rows:
            ch_key = row["order__sales_channel__identifier"] or "unknown"
            ch_label = self._label(row["order__sales_channel__label"]) \
                or ch_key
            se_key = str(row["subevent"]) if row["subevent"] else "event"
            se_label = self._label(row["subevent__name"]) or str(_("Event"))
            cat_name = self._label(row["item__name"]) or str(_("Product"))
            nature = self._label(row["variation__value"]) or str(DEFAULT_NATURE)
            count = row["count"] or 0
            gross = row["gross"] or ZERO

            channel = channels.setdefault(
                ch_key, RecetteChannel(key=ch_key, label=ch_label)
            )
            session = self._get_or_add_session(channel, se_key, se_label)
            category = self._get_or_add_category(session, cat_name)
            category.lines.append(
                RecetteLine(
                    category=cat_name,
                    nature=nature,
                    count=count,
                    gross=gross,
                )
            )

        report.channels = list(channels.values())

    @staticmethod
    def _get_or_add_session(channel: RecetteChannel, key, label):
        for s in channel.sessions:
            if s.key == key:
                return s
        s = RecetteSession(key=key, label=label)
        channel.sessions.append(s)
        return s

    @staticmethod
    def _get_or_add_category(session: RecetteSession, name):
        for c in session.categories:
            if c.name == name:
                return c
        c = RecetteCategory(name=name)
        session.categories.append(c)
        return c

    @staticmethod
    def _label(value) -> str:
        """Normalize an i18n/text field to a plain string.

        Pretix name/value fields may be LazyI18nString or plain text; str()
        yields the active-language rendering for the former.
        """
        if value is None:
            return ""
        return str(value)
