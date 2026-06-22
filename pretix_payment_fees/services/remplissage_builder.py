"""
RemplissageBuilder: venue-occupancy data for the "Remplissage de salle" export
(STORY-202).

Produces NO monetary value. Two blocks:
  - categories: paid / invitations / total per Item (reuses ticketing logic)
  - quotas: sold / capacity / fill rate (%) per Pretix Quota

A quota groups several items; a sold count is the number of paid positions for
the quota's items (deduplicated by position). When a quota has no size (Pretix
unlimited), the rate is undefined and only the sold count is shown.
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional

from django.db.models import Count
from django.utils.translation import gettext_lazy as _
from pretix.base.models import Item, OrderPosition, Quota

from .recette_builder import DEFAULT_STATUSES


@dataclass
class CategoryCount:
    name: str
    paid: int = 0
    free: int = 0

    @property
    def total(self) -> int:
        return self.paid + self.free


@dataclass
class QuotaFill:
    name: str
    size: Optional[int]                 # capacity, None = unlimited
    sold: int = 0

    @property
    def rate(self) -> Optional[Decimal]:
        """Fill rate in percent, or None when capacity is unlimited/zero."""
        if not self.size:
            return None
        return (Decimal(self.sold) * 100 / Decimal(self.size)).quantize(
            Decimal("0.1")
        )

    @property
    def rate_display(self) -> str:
        r = self.rate
        if r is None:
            return ""
        return f"{r:.1f} %".replace(".", ",")


@dataclass
class RemplissageReport:
    categories: List[CategoryCount] = field(default_factory=list)
    quotas: List[QuotaFill] = field(default_factory=list)

    @property
    def total_paid(self) -> int:
        return sum(c.paid for c in self.categories)

    @property
    def total_free(self) -> int:
        return sum(c.free for c in self.categories)

    @property
    def total_places(self) -> int:
        return self.total_paid + self.total_free

    @property
    def has_quota_sizes(self) -> bool:
        """True if at least one quota has a finite capacity (-> show rate col)."""
        return any(q.size for q in self.quotas)


class RemplissageBuilder:
    """Build a RemplissageReport (categories + quotas), no monetary values."""

    def __init__(self, events, form_data: Optional[dict] = None):
        self.events = list(events)
        self.form_data = form_data or {}
        self.statuses = self.form_data.get("statuses") or DEFAULT_STATUSES
        self.channel = self.form_data.get("channel") or None

    def build(self) -> RemplissageReport:
        event_ids = [e.pk for e in self.events]
        report = RemplissageReport()
        if not event_ids:
            return report
        report.categories = self._categories(event_ids)
        report.quotas = self._quotas(event_ids)
        return report

    # -- internals ----------------------------------------------------------

    def _channel_pos_filter(self) -> dict:
        if self.channel:
            return {"order__sales_channel__identifier": self.channel}
        return {}

    def _categories(self, event_ids):
        from django.db.models import Q

        rows = (
            OrderPosition.objects.filter(
                order__event_id__in=event_ids,
                order__status__in=self.statuses,
                **self._channel_pos_filter(),
            )
            .values("item__name")
            .annotate(
                paid=Count("id", filter=Q(price__gt=0)),
                free=Count("id", filter=Q(price=0)),
            )
            .order_by("item__name")
        )
        out = []
        for row in rows:
            out.append(CategoryCount(
                name=str(row["item__name"]) or str(_("Product")),
                paid=row["paid"] or 0,
                free=row["free"] or 0,
            ))
        return out

    def _quotas(self, event_ids):
        """Sold per quota = paid positions of the quota's items (deduplicated).

        Counts positions whose item belongs to the quota. An item in several
        quotas is counted in each (quotas are independent capacity buckets in
        Pretix), but within one quota each position counts once.
        """
        out = []
        quotas = Quota.objects.filter(event_id__in=event_ids)
        for q in quotas:
            item_ids = list(q.items.values_list("id", flat=True))
            if not item_ids:
                continue
            qs = OrderPosition.objects.filter(
                order__event_id__in=event_ids,
                order__status__in=self.statuses,
                item_id__in=item_ids,
                **self._channel_pos_filter(),
            )
            if q.subevent_id:
                qs = qs.filter(subevent_id=q.subevent_id)
            sold = qs.count()
            out.append(QuotaFill(name=str(q.name), size=q.size, sold=sold))
        out.sort(key=lambda x: x.name)
        return out
