"""
RecetteDataBuilder: revenue aggregation service for the "Recette
Manifestation" accounting export.

This service turns Pretix orders into a neutral, render-agnostic data
structure so that the PDF and CSV/Excel renderers consume exactly the same
totals without duplicating business logic.

STORY-100 scope: base aggregation.
    Sales channel -> Session (subevent) -> Category (Item) -> Nature (Variation)
    Measures: count, unit price, gross revenue, per-category subtotals, grand total.

STORY-101 scope: fee breakdown.
    Dynamic fee columns, one per PSP (OrderFee.internal_type) and per native
    fee_type present. Fees aggregate at the order level (an OrderFee belongs to
    an Order, not to a position), hence per channel / per session / per total.
    Net revenue = gross minus fees. Reconciliation against PSPTransactionCache.

Out of scope here (later stories):
    - Channel/session fine logic and cross view (STORY-102)
    - Ticketing block and VAT (STORY-103)
    - Any rendering (STORY-104, 105)

Design rules (frozen in STORY-000):
    - Pretix native vocabulary (Product, Gross, Count...).
    - One fee column per PSP (internal_type), generated dynamically.
    - The builder performs NO rendering: it knows nothing about PDF or CSV.
"""

from collections import OrderedDict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional

from django.db.models import Count, Sum
from django.utils.translation import gettext_lazy as _
from pretix.base.models import Order, OrderFee, OrderPosition

# Order statuses included in the report perimeter. Paid orders only; positions
# priced at 0 (invitations / free admissions) are kept (they have a count but
# zero gross). Canceled/expired orders are excluded. The status set is made
# overridable through form_data later (STORY-106).
DEFAULT_STATUSES = (Order.STATUS_PAID,)

# Displayed when an order position has no variation.
DEFAULT_NATURE = _("(default)")

ZERO = Decimal("0.00")

# Human-readable labels for known PSP internal_types (frozen in STORY-000).
# Unknown types fall back to a humanized label (see fee_label()).
PSP_LABELS = {
    "mollie_creditcard_fee": _("Mollie fee (card)"),
    "mollie_ideal_fee": _("Mollie fee (iDEAL)"),
    "mollie_bancontact_fee": _("Mollie fee (Bancontact)"),
    "sumup_fee": _("SumUp fee"),
}

# Labels for native OrderFee.fee_type values used when internal_type is empty.
FEE_TYPE_LABELS = {
    OrderFee.FEE_TYPE_PAYMENT: _("Payment fee"),
    OrderFee.FEE_TYPE_SERVICE: _("Service fee"),
    OrderFee.FEE_TYPE_SHIPPING: _("Shipping fee"),
    OrderFee.FEE_TYPE_CANCELLATION: _("Cancellation fee"),
    OrderFee.FEE_TYPE_INSURANCE: _("Insurance fee"),
    OrderFee.FEE_TYPE_LATE: _("Late fee"),
    OrderFee.FEE_TYPE_OTHER: _("Other fees"),
    OrderFee.FEE_TYPE_GIFTCARD: _("Gift card"),
}


def fee_label(key: str, fee_type: str = "") -> str:
    """Readable column label for a fee key (internal_type or fee_type).

    `key` is the internal_type when present, else the fee_type. Falls back to a
    humanized rendering for unknown PSP internal_types (e.g. "xyz_fee" -> "Xyz
    fee").
    """
    if key in PSP_LABELS:
        return str(PSP_LABELS[key])
    if key in FEE_TYPE_LABELS:
        return str(FEE_TYPE_LABELS[key])
    base = key.replace("_fee", "").replace("_", " ").strip()
    return (base.title() + " " + str(_("fee"))).strip()


@dataclass
class FeeColumn:
    """A dynamic fee column (one PSP / one fee type present in the data)."""

    key: str                            # internal_type, or fee_type if empty
    label: str                          # human-readable header


def _sum_fee_dicts(dicts) -> Dict[str, Decimal]:
    """Sum a list of {fee_key: amount} dicts into a single dict."""
    out: Dict[str, Decimal] = {}
    for d in dicts:
        for k, v in d.items():
            out[k] = out.get(k, ZERO) + v
    return out


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
    """A session group (one subevent, or the event if none).

    Fees aggregate at the order level, so they are carried on the session (the
    finest grouping that an OrderFee can be attributed to via its order's
    channel and subevent), not on individual product lines.
    """

    key: str                            # stable key (subevent id or 'event')
    label: str                          # human label (subevent/event name+date)
    categories: List[RecetteCategory] = field(default_factory=list)
    fees: Dict[str, Decimal] = field(default_factory=dict)  # {fee_key: amount}

    @property
    def count(self) -> int:
        return sum(c.count for c in self.categories)

    @property
    def gross(self) -> Decimal:
        return sum((c.gross for c in self.categories), ZERO)

    @property
    def fees_total(self) -> Decimal:
        return sum(self.fees.values(), ZERO)

    @property
    def net(self) -> Decimal:
        """Net revenue = gross minus fees."""
        return self.gross - self.fees_total


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

    @property
    def fees(self) -> Dict[str, Decimal]:
        return _sum_fee_dicts(s.fees for s in self.sessions)

    @property
    def fees_total(self) -> Decimal:
        return sum(self.fees.values(), ZERO)

    @property
    def net(self) -> Decimal:
        return self.gross - self.fees_total


@dataclass
class RecetteReport:
    """Top-level neutral structure returned by the builder."""

    currency: str
    channels: List[RecetteChannel] = field(default_factory=list)
    fee_columns: List[FeeColumn] = field(default_factory=list)

    @property
    def count(self) -> int:
        return sum(c.count for c in self.channels)

    @property
    def gross(self) -> Decimal:
        return sum((c.gross for c in self.channels), ZERO)

    @property
    def fees(self) -> Dict[str, Decimal]:
        return _sum_fee_dicts(c.fees for c in self.channels)

    @property
    def fees_total(self) -> Decimal:
        return sum(self.fees.values(), ZERO)

    @property
    def net(self) -> Decimal:
        return self.gross - self.fees_total


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

        fee_rows = self._aggregate_fees(event_ids)
        self._fill_fees(report, fee_rows)
        return report

    def reconcile_with_cache(self, report: RecetteReport) -> dict:
        """Cross-check the report's PSP fees against PSPTransactionCache.

        Source of truth for the report is OrderFee (it lives on the order and
        is attributable to a channel). PSPTransactionCache is an independent
        record of real PSP settlements, used here only for reconciliation /
        diagnostics: it does NOT change any reported figure.

        Returns a dict {provider: {"report": Decimal, "cache": Decimal,
        "delta": Decimal}}. Returns an empty dict if the cache model is
        unavailable. Best-effort: never raises into the report build.
        """
        try:
            from ..models import PSPTransactionCache
        except Exception:
            return {}

        # Map report fee keys to a PSP provider name for comparison.
        def provider_of(key: str) -> Optional[str]:
            if key.startswith("mollie"):
                return "mollie"
            if key.startswith("sumup"):
                return "sumup"
            return None

        report_by_provider: Dict[str, Decimal] = {}
        for key, amount in report.fees.items():
            provider = provider_of(key)
            if provider:
                report_by_provider[provider] = (
                    report_by_provider.get(provider, ZERO) + amount
                )

        organizer_ids = {e.organizer_id for e in self.events}
        result = {}
        for provider, reported in report_by_provider.items():
            cache_total = (
                PSPTransactionCache.objects.filter(
                    organizer_id__in=organizer_ids, psp_provider=provider
                ).aggregate(total=Sum("amount_fee"))["total"]
                or ZERO
            )
            result[provider] = {
                "report": reported,
                "cache": cache_total,
                "delta": reported - cache_total,
            }
        return result

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

    def _aggregate_fees(self, event_ids):
        """Aggregated ORM query over OrderFee, grouped by channel and fee key.

        An OrderFee belongs to an Order (not to a position), so fees are
        attributed via the order's sales channel. The fee key is the
        internal_type when present, else the fee_type. No per-order Python loop.

        Returns dict rows with keys:
            channel, fee_type, internal_type, total
        """
        return (
            OrderFee.objects.filter(
                order__event_id__in=event_ids,
                order__status__in=self.statuses,
            )
            .values(
                "order__sales_channel__identifier",
                "fee_type",
                "internal_type",
            )
            .annotate(total=Sum("value"))
            .order_by("order__sales_channel__identifier", "fee_type")
        )

    def _fill_fees(self, report: RecetteReport, fee_rows):
        """Attach fee totals to channels and declare the dynamic fee columns.

        Fees are deposited on the channel's sessions. With a single session per
        channel (common case) the whole channel fee lands on it. With several
        sessions, the fee is put on the first session of the channel; finer
        per-session attribution is handled in STORY-102.
        """
        channels_by_key = {c.key: c for c in report.channels}
        columns: "OrderedDict[str, FeeColumn]" = OrderedDict()

        for row in fee_rows:
            ch_key = row["order__sales_channel__identifier"] or "unknown"
            fee_type = row["fee_type"] or ""
            internal_type = row["internal_type"] or ""
            key = internal_type or fee_type or "fee"
            total = row["total"] or ZERO

            if key not in columns:
                columns[key] = FeeColumn(key=key, label=fee_label(key, fee_type))

            channel = channels_by_key.get(ch_key)
            if channel is None or not channel.sessions:
                # Fees on a channel that produced no paid position (edge case):
                # skip rather than fabricate an empty section.
                continue
            session = channel.sessions[0]
            session.fees[key] = session.fees.get(key, ZERO) + total

        report.fee_columns = list(columns.values())

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
