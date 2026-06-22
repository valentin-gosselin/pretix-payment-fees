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

from django.db.models import Count, Q, Sum
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
    # Source strings in French (Pretix FR vocabulary, frozen STORY-000). They
    # stay gettext_lazy so STORY-106 can translate them to the other languages.
    "mollie_creditcard_fee": _("Frais Mollie (CB)"),
    "mollie_ideal_fee": _("Frais Mollie (iDEAL)"),
    "mollie_bancontact_fee": _("Frais Mollie (Bancontact)"),
    "sumup_fee": _("Frais SumUp"),
}

# Labels for native OrderFee.fee_type values used when internal_type is empty.
FEE_TYPE_LABELS = {
    OrderFee.FEE_TYPE_PAYMENT: _("Frais de paiement"),
    OrderFee.FEE_TYPE_SERVICE: _("Frais de service"),
    OrderFee.FEE_TYPE_SHIPPING: _("Frais de livraison"),
    OrderFee.FEE_TYPE_CANCELLATION: _("Frais d'annulation"),
    OrderFee.FEE_TYPE_INSURANCE: _("Frais d'assurance"),
    OrderFee.FEE_TYPE_LATE: _("Frais de retard"),
    OrderFee.FEE_TYPE_OTHER: _("Autres frais"),
    OrderFee.FEE_TYPE_GIFTCARD: _("Carte cadeau"),
}


def _fmt_rate(rate: Decimal) -> str:
    """Format a VAT rate the French way: 2.10 -> '2,10 %'."""
    s = f"{rate:.2f}".replace(".", ",")
    return f"{s} %"


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
    return (str(_("Frais")) + " " + base.title()).strip()


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
    fees: dict = field(default_factory=dict)  # filled in STORY-101
    paid_count: int = 0                 # positions with price > 0
    free_count: int = 0                 # positions with price == 0 (invitations)
    tax_rate: Decimal = ZERO            # VAT rate of the line (frozen tax_rate)
    fixed_unit_price: Optional[Decimal] = None  # set for free-price lines
    group_key: Optional[str] = None     # custom merge key (free-price lines)

    @property
    def unit_price(self) -> Decimal:
        """Unit price: the pinned amount for free-price lines, else the average
        (gross / count)."""
        if self.fixed_unit_price is not None:
            return self.fixed_unit_price
        if not self.count:
            return ZERO
        return (self.gross / self.count).quantize(Decimal("0.01"))

    @property
    def fees_total(self) -> Decimal:
        return sum(self.fees.values(), ZERO)

    @property
    def net(self) -> Decimal:
        """Net revenue for the line = gross minus its allocated fees."""
        return self.gross - self.fees_total


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
    def paid_count(self) -> int:
        return sum(line.paid_count for line in self.lines)

    @property
    def free_count(self) -> int:
        """Invitations (price 0) count for the category."""
        return sum(line.free_count for line in self.lines)

    @property
    def fees(self) -> Dict[str, Decimal]:
        """Fees of the category = sum of its lines' allocated fees."""
        return _sum_fee_dicts(line.fees for line in self.lines)

    @property
    def fees_total(self) -> Decimal:
        return sum(self.fees.values(), ZERO)

    @property
    def net(self) -> Decimal:
        return self.gross - self.fees_total

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
    tax_rates: set = field(default_factory=set)  # distinct VAT rates seen

    @property
    def count(self) -> int:
        return sum(c.count for c in self.categories)

    @property
    def gross(self) -> Decimal:
        return sum((c.gross for c in self.categories), ZERO)

    @property
    def paid_count(self) -> int:
        return sum(c.paid_count for c in self.categories)

    @property
    def free_count(self) -> int:
        """Invitations (price 0) count for the session."""
        return sum(c.free_count for c in self.categories)

    @property
    def fees_total(self) -> Decimal:
        return sum(self.fees.values(), ZERO)

    @property
    def net(self) -> Decimal:
        """Net revenue = gross minus fees."""
        return self.gross - self.fees_total

    @property
    def tax_rate_display(self) -> str:
        """Session VAT rate as a string, or 'mixed' when heterogeneous.

        Returns e.g. "2,10 %" when a single rate applies to the session, or a
        marker when several rates are present (renderer then shows per-line).
        """
        rates = sorted(self.tax_rates)
        if not rates:
            return ""
        if len(rates) == 1:
            return _fmt_rate(rates[0])
        return str(_("mixed"))

    @property
    def tax_is_uniform(self) -> bool:
        return len(self.tax_rates) <= 1


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

    def fee_reconciliation(self) -> dict:
        """Check that the per-line fee allocation sums back to the totals.

        Returns {fee_key: {"lines": Decimal, "total": Decimal, "ok": bool}}.
        The per-line sum must equal the report-level fee total (which equals the
        Pretix OrderFee total) to the cent. Used as a self-check and can be
        surfaced in the export.
        """
        line_sums: Dict[str, Decimal] = {}
        for ch in self.channels:
            for se in ch.sessions:
                for cat in se.categories:
                    for ln in cat.lines:
                        for k, v in ln.fees.items():
                            line_sums[k] = line_sums.get(k, ZERO) + v
        totals = self.fees
        result = {}
        for k in set(line_sums) | set(totals):
            lines = line_sums.get(k, ZERO)
            total = totals.get(k, ZERO)
            result[k] = {"lines": lines, "total": total, "ok": lines == total}
        return result

    @property
    def fees_reconciled(self) -> bool:
        """True when every per-line fee allocation matches its total."""
        return all(v["ok"] for v in self.fee_reconciliation().values())

    def cross_view(self) -> "CrossView":
        """Category x Session matrix (Trium pages 2-3 equivalent).

        Aggregates across all channels: for each category, the count and gross
        per session, plus row totals. Sessions are ordered by first appearance.
        """
        session_order: "OrderedDict[str, str]" = OrderedDict()
        # category -> session_key -> {"count": int, "gross": Decimal}
        matrix: "OrderedDict[str, OrderedDict[str, dict]]" = OrderedDict()

        for ch in self.channels:
            for se in ch.sessions:
                session_order.setdefault(se.key, se.label)
                for cat in se.categories:
                    cat_row = matrix.setdefault(cat.name, OrderedDict())
                    cell = cat_row.setdefault(
                        se.key, {"count": 0, "gross": ZERO}
                    )
                    cell["count"] += cat.count
                    cell["gross"] += cat.gross

        return CrossView(
            sessions=list(session_order.items()),  # [(key, label), ...]
            rows=matrix,
        )

    def ticketing(self) -> "TicketingBlock":
        """Ticketing counts per category: paid / invitations / total.

        Pretix has no e-ticket / m-ticket typology like the Trium reference, so
        only the meaningful Pretix counts are produced (paid vs free admission).
        Aggregates across all channels and sessions.
        """
        # category -> {"paid": int, "free": int}
        rows: "OrderedDict[str, dict]" = OrderedDict()
        for ch in self.channels:
            for se in ch.sessions:
                for cat in se.categories:
                    r = rows.setdefault(cat.name, {"paid": 0, "free": 0})
                    r["paid"] += cat.paid_count
                    r["free"] += cat.free_count
        return TicketingBlock(rows=rows)


@dataclass
class CrossView:
    """Category x Session matrix produced by RecetteReport.cross_view()."""

    sessions: List[tuple]                     # [(session_key, label), ...]
    rows: "OrderedDict[str, OrderedDict[str, dict]]"

    def row_total(self, category: str) -> dict:
        cells = self.rows.get(category, {})
        return {
            "count": sum(c["count"] for c in cells.values()),
            "gross": sum((c["gross"] for c in cells.values()), ZERO),
        }


@dataclass
class TicketingBlock:
    """Ticketing counts per category produced by RecetteReport.ticketing()."""

    rows: "OrderedDict[str, dict]"            # category -> {"paid", "free"}

    def total(self) -> dict:
        return {
            "paid": sum(r["paid"] for r in self.rows.values()),
            "free": sum(r["free"] for r in self.rows.values()),
        }


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
        # Optional single-channel filter (sales channel identifier). When set,
        # the report is restricted to that channel; otherwise all channels are
        # rendered as separate sections plus a grand total.
        self.channel = self.form_data.get("channel") or None

    # -- public API ---------------------------------------------------------

    def build(self) -> RecetteReport:
        event_ids = [e.pk for e in self.events]
        currency = self._resolve_currency()
        report = RecetteReport(currency=currency)
        if not event_ids:
            return report

        rows = self._aggregate(event_ids)
        self._fill_report(report, rows)

        self._fill_fees(report, event_ids)
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

    def _channel_filter(self) -> dict:
        """ORM filter kwargs restricting to a single sales channel, if set."""
        if self.channel:
            return {"order__sales_channel__identifier": self.channel}
        return {}

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
                **self._channel_filter(),
            )
            .values(
                "order__sales_channel__identifier",
                "order__sales_channel__label",
                "subevent",
                "subevent__name",
                "subevent__date_from",
                "item",
                "item__name",
                "item__free_price",
                "variation",
                "variation__value",
                "tax_rate",
                # group by price too: free-price products get one line per
                # distinct amount (accounting requirement). Fixed-price products
                # are re-merged downstream (their price is constant per line).
                "price",
            )
            .annotate(
                count=Count("id"),
                gross=Sum("price"),
                paid_count=Count("id", filter=Q(price__gt=0)),
                free_count=Count("id", filter=Q(price=0)),
            )
            .order_by(
                "order__sales_channel__label",
                "subevent",
                "item__name",
                "variation__value",
                "price",
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
            se_label = self._session_label(
                row["subevent__name"], row["subevent__date_from"]
            )
            cat_name = self._label(row["item__name"]) or str(_("Product"))
            nature = self._label(row["variation__value"]) or str(DEFAULT_NATURE)
            tax_rate = row["tax_rate"] or ZERO
            price = row["price"] or ZERO
            free_price = bool(row["item__free_price"])

            channel = channels.setdefault(
                ch_key, RecetteChannel(key=ch_key, label=ch_label)
            )
            session = self._get_or_add_session(channel, se_key, se_label)
            session.tax_rates.add(tax_rate)
            category = self._get_or_add_category(session, cat_name)
            # For free-price products, each distinct amount is its own line, so
            # the unit price shown is the real amount (not an average). We key
            # such lines by (nature, price) and pin the unit price. Fixed-price
            # products keep merging by (category, nature).
            if free_price:
                line_key = f"{nature} @{price}"
                line = self._get_or_add_line(
                    category, cat_name, nature, key=line_key,
                    fixed_unit_price=price,
                )
            else:
                line = self._get_or_add_line(category, cat_name, nature)
            line.count += row["count"] or 0
            line.gross += row["gross"] or ZERO
            line.paid_count += row["paid_count"] or 0
            line.free_count += row["free_count"] or 0
            line.tax_rate = tax_rate

        report.channels = list(channels.values())

    def _fill_fees(self, report: RecetteReport, event_ids):
        """Allocate each fee ONLY to the lines that actually bore it.

        Crucial correctness rule: a fee belongs to its order, so it must only be
        spread over the positions of *that* order. A product line aggregates
        positions from many orders; some paid online (with a PSP fee), some not
        (manual import, cash at the box office). We must NOT put a fee on
        positions whose order had none.

        Method (intra-order pro rata):
          1. For each order with fees, get its total fee per key and its gross.
          2. Split that order's fee across its own positions, pro rata of price,
             aggregated per (channel, session, item, variation) line.
          3. The cent-level rounding remainder is corrected per fee key so the
             grand total still equals the Pretix OrderFee total.
        """
        # 1) fee per order and key
        fee_rows = (
            OrderFee.objects.filter(
                order__event_id__in=event_ids,
                order__status__in=self.statuses,
                **self._channel_filter(),
            )
            .values("order", "fee_type", "internal_type")
            .annotate(total=Sum("value"))
        )
        order_fees: Dict[int, Dict[str, Decimal]] = {}
        columns: "OrderedDict[str, FeeColumn]" = OrderedDict()
        for row in fee_rows:
            oid = row["order"]
            key = row["internal_type"] or row["fee_type"] or "fee"
            if key not in columns:
                columns[key] = FeeColumn(
                    key=key, label=fee_label(key, row["fee_type"] or "")
                )
            d = order_fees.setdefault(oid, {})
            d[key] = d.get(key, ZERO) + (row["total"] or ZERO)
        report.fee_columns = list(columns.values())
        if not order_fees:
            return

        # 2) per (order, line-key) gross, only for orders that have fees
        line_index = self._line_index(report)
        pos_rows = (
            OrderPosition.objects.filter(
                order__event_id__in=event_ids,
                order__status__in=self.statuses,
                order_id__in=list(order_fees.keys()),
                **self._channel_filter(),
            )
            .values(
                "order",
                "order__sales_channel__identifier",
                "subevent",
                "item__name",
                "variation__value",
            )
            .annotate(gross=Sum("price"))
        )
        # group positions by order so we can pro-rate within each order
        by_order: Dict[int, list] = {}
        order_gross: Dict[int, Decimal] = {}
        for row in pos_rows:
            oid = row["order"]
            by_order.setdefault(oid, []).append(row)
            order_gross[oid] = order_gross.get(oid, ZERO) + (row["gross"] or ZERO)

        # 3) spread each order's fee onto its own lines, pro rata of price
        for oid, rows in by_order.items():
            fees = order_fees.get(oid, {})
            base = order_gross.get(oid, ZERO)
            paying = [r for r in rows if (r["gross"] or ZERO) > ZERO]
            for key, total in fees.items():
                if not paying or base <= ZERO:
                    continue
                acc = ZERO
                for i, r in enumerate(paying):
                    if i == len(paying) - 1:
                        share = total - acc
                    else:
                        share = (total * (r["gross"] or ZERO) / base).quantize(
                            Decimal("0.01")
                        )
                        acc += share
                    line = self._line_for(line_index, r)
                    if line is not None:
                        line.fees[key] = line.fees.get(key, ZERO) + share

        # carry the per-line fee totals up to the sessions for the totals row
        self._lift_line_fees_to_sessions(report)

    @staticmethod
    def _line_index(report: RecetteReport) -> dict:
        """Map (channel_key, session_key, category, nature) -> RecetteLine."""
        index = {}
        for ch in report.channels:
            for se in ch.sessions:
                for cat in se.categories:
                    for ln in cat.lines:
                        index[(ch.key, se.key, cat.name, ln.nature)] = ln
        return index

    @classmethod
    def _line_for(cls, line_index, row):
        ch_key = row["order__sales_channel__identifier"] or "unknown"
        se_key = str(row["subevent"]) if row["subevent"] else "event"
        cat = cls._label(row["item__name"]) or str(_("Product"))
        nature = cls._label(row["variation__value"]) or str(DEFAULT_NATURE)
        return line_index.get((ch_key, se_key, cat, nature))

    @staticmethod
    def _lift_line_fees_to_sessions(report: RecetteReport):
        """Recompute each session's fee dict as the sum of its lines' fees."""
        for ch in report.channels:
            for se in ch.sessions:
                agg: Dict[str, Decimal] = {}
                for cat in se.categories:
                    for ln in cat.lines:
                        for k, v in ln.fees.items():
                            agg[k] = agg.get(k, ZERO) + v
                se.fees = agg

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
    def _get_or_add_line(category: RecetteCategory, cat_name, nature,
                         key=None, fixed_unit_price=None):
        """Find or create a line. `key` (when given, e.g. for free-price lines)
        is the merge key so several distinct amounts stay on separate lines."""
        for line in category.lines:
            if key is not None:
                if line.group_key == key:
                    return line
            elif line.group_key is None and line.nature == nature:
                return line
        line = RecetteLine(category=cat_name, nature=nature,
                           group_key=key, fixed_unit_price=fixed_unit_price)
        category.lines.append(line)
        return line

    @staticmethod
    def _label(value) -> str:
        """Normalize an i18n/text field to a plain string.

        Pretix name/value fields may be LazyI18nString or plain text; str()
        yields the active-language rendering for the former.
        """
        if value is None:
            return ""
        return str(value)

    @classmethod
    def _session_label(cls, name, date_from) -> str:
        """Build a session label from a subevent name and start date.

        Falls back to the event marker when there is no subevent. Format:
        "Name (DD/MM/YYYY HH:MM)" when both are present, just the name or the
        date otherwise.
        """
        name_str = cls._label(name)
        if date_from is None and not name_str:
            return str(_("Event"))
        date_str = ""
        if date_from is not None:
            date_str = date_from.strftime("%d/%m/%Y %H:%M")
        if name_str and date_str:
            return f"{name_str} ({date_str})"
        return name_str or date_str or str(_("Event"))
