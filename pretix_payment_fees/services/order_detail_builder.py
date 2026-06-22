"""
OrderDetailBuilder: per-order aggregation for the "Détail par commande" export
(STORY-200, revised STORY-201+).

An order with several product types yields one product line per (product, price),
grouped under the order. Order-level columns (code/date/channel) are filled on
the first line only by the renderer. Amount and fees are split per product line:
the order fee is allocated to its own product lines pro rata of gross (so the
per-line fee sum equals the Pretix OrderFee total exactly).

No personal data (no email/name) is ever selected (GDPR).
"""
from collections import OrderedDict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional

from django.db.models import Count, Sum
from django.utils.translation import gettext_lazy as _
from pretix.base.models import Order, OrderFee, OrderPosition

from .recette_builder import DEFAULT_STATUSES, FeeColumn, fee_label

ZERO = Decimal("0.00")


@dataclass
class ProductLine:
    """One (product, price) line within an order."""

    product: str                        # item name
    count: int = 0                      # number of identical positions
    gross: Decimal = ZERO               # sum of their prices
    fees: Dict[str, Decimal] = field(default_factory=dict)

    @property
    def unit_price(self) -> Decimal:
        if not self.count:
            return ZERO
        return (self.gross / self.count).quantize(Decimal("0.01"))

    @property
    def fees_total(self) -> Decimal:
        return sum(self.fees.values(), ZERO)

    @property
    def net(self) -> Decimal:
        return self.gross - self.fees_total


@dataclass
class OrderDetailRow:
    """One order, holding its product lines. Carries NO personal data."""

    code: str
    datetime: object
    channel: str
    lines: List[ProductLine] = field(default_factory=list)

    @property
    def count(self) -> int:
        return sum(line.count for line in self.lines)

    @property
    def gross(self) -> Decimal:
        return sum((line.gross for line in self.lines), ZERO)

    @property
    def fees(self) -> Dict[str, Decimal]:
        out: Dict[str, Decimal] = {}
        for line in self.lines:
            for k, v in line.fees.items():
                out[k] = out.get(k, ZERO) + v
        return out

    @property
    def fees_total(self) -> Decimal:
        return sum(self.fees.values(), ZERO)

    @property
    def net(self) -> Decimal:
        return self.gross - self.fees_total


@dataclass
class OrderDetailReport:
    currency: str
    rows: List[OrderDetailRow] = field(default_factory=list)
    fee_columns: list = field(default_factory=list)

    @property
    def order_count(self) -> int:
        return len(self.rows)

    @property
    def count(self) -> int:
        return sum(r.count for r in self.rows)

    @property
    def gross(self) -> Decimal:
        return sum((r.gross for r in self.rows), ZERO)

    @property
    def fees(self) -> Dict[str, Decimal]:
        out: Dict[str, Decimal] = {}
        for r in self.rows:
            for k, v in r.fees.items():
                out[k] = out.get(k, ZERO) + v
        return out

    @property
    def fees_total(self) -> Decimal:
        return sum(self.fees.values(), ZERO)

    @property
    def net(self) -> Decimal:
        return self.gross - self.fees_total

    def fee_reconciliation(self) -> dict:
        lines_sum: Dict[str, Decimal] = {}
        for r in self.rows:
            for line in r.lines:
                for k, v in line.fees.items():
                    lines_sum[k] = lines_sum.get(k, ZERO) + v
        totals = self.fees
        return {
            k: {
                "lines": lines_sum.get(k, ZERO),
                "total": totals.get(k, ZERO),
                "ok": lines_sum.get(k, ZERO) == totals.get(k, ZERO),
            }
            for k in set(lines_sum) | set(totals)
        }

    @property
    def fees_reconciled(self) -> bool:
        return all(v["ok"] for v in self.fee_reconciliation().values())


class OrderDetailBuilder:
    """Aggregate Pretix orders into a per-order, per-product OrderDetailReport."""

    def __init__(self, events, form_data: Optional[dict] = None):
        self.events = list(events)
        self.form_data = form_data or {}
        self.statuses = self.form_data.get("statuses") or DEFAULT_STATUSES
        self.channel = self.form_data.get("channel") or None

    def build(self) -> OrderDetailReport:
        event_ids = [e.pk for e in self.events]
        report = OrderDetailReport(currency=self._currency())
        if not event_ids:
            return report

        orders = self._aggregate_orders(event_ids)
        self._aggregate_lines(event_ids, orders)
        self._allocate_fees(event_ids, orders, report)
        report.rows = sorted(
            orders.values(), key=lambda r: (r.datetime or 0, r.code)
        )
        return report

    # -- internals ----------------------------------------------------------

    def _currency(self) -> str:
        cur = {getattr(e, "currency", None) for e in self.events}
        cur.discard(None)
        return cur.pop() if len(cur) == 1 else (sorted(cur)[0] if cur else "")

    def _channel_filter(self) -> dict:
        if self.channel:
            return {"sales_channel__identifier": self.channel}
        return {}

    def _pos_channel_filter(self) -> dict:
        return {f"order__{k}": v for k, v in self._channel_filter().items()}

    def _aggregate_orders(self, event_ids):
        # event timezone per event id, to show the order time locally (needed
        # for order-by-order reconciliation with the PSP settlements)
        tz_by_event = {e.pk: getattr(e, "timezone", None) for e in self.events}
        rows = (
            Order.objects.filter(
                event_id__in=event_ids, status__in=self.statuses,
                **self._channel_filter(),
            )
            .values("pk", "code", "datetime", "event_id",
                    "sales_channel__identifier", "sales_channel__label")
        )
        out: "OrderedDict[int, OrderDetailRow]" = OrderedDict()
        for row in rows:
            dt = row["datetime"]
            tz = tz_by_event.get(row["event_id"])
            if dt is not None and tz is not None:
                dt = dt.astimezone(tz)
            out[row["pk"]] = OrderDetailRow(
                code=row["code"],
                datetime=dt,
                channel=str(row["sales_channel__label"]
                            or row["sales_channel__identifier"] or ""),
            )
        return out

    def _aggregate_lines(self, event_ids, orders):
        """One product line per (order, item, price): count + gross."""
        rows = (
            OrderPosition.objects.filter(
                order__event_id__in=event_ids,
                order__status__in=self.statuses,
                **self._pos_channel_filter(),
            )
            .values("order", "item__name", "price")
            .annotate(n=Count("id"), gross=Sum("price"))
            .order_by("order", "item__name", "price")
        )
        for row in rows:
            o = orders.get(row["order"])
            if o is None:
                continue
            o.lines.append(ProductLine(
                product=str(row["item__name"]) or str(_("Product")),
                count=row["n"] or 0,
                gross=row["gross"] or ZERO,
            ))

    def _allocate_fees(self, event_ids, orders, report):
        """Per (order, fee key) total -> split over the order's product lines
        pro rata of gross (last paying line absorbs rounding)."""
        rows = (
            OrderFee.objects.filter(
                order__event_id__in=event_ids,
                order__status__in=self.statuses,
                **self._pos_channel_filter(),
            )
            .values("order", "fee_type", "internal_type")
            .annotate(total=Sum("value"))
        )
        columns: "OrderedDict[str, FeeColumn]" = OrderedDict()
        for row in rows:
            o = orders.get(row["order"])
            if o is None:
                continue
            fee_type = row["fee_type"] or ""
            key = row["internal_type"] or fee_type or "fee"
            if key not in columns:
                columns[key] = FeeColumn(key=key, label=fee_label(key, fee_type))
            self._spread(o, key, row["total"] or ZERO)
        report.fee_columns = list(columns.values())

    @staticmethod
    def _spread(order: OrderDetailRow, key: str, total: Decimal):
        paying = [ln for ln in order.lines if ln.gross > ZERO]
        base = sum((ln.gross for ln in paying), ZERO)
        if not paying or base <= ZERO:
            return
        acc = ZERO
        for i, ln in enumerate(paying):
            if i == len(paying) - 1:
                share = total - acc
            else:
                share = (total * ln.gross / base).quantize(Decimal("0.01"))
                acc += share
            ln.fees[key] = ln.fees.get(key, ZERO) + share
