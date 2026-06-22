"""
"Détail par commande" exporter (STORY-201).

Lists orders, one row each, with category breakdown and real PSP fees per
provider. No personal data (GDPR). PDF / CSV / Excel.
"""
from collections import OrderedDict

from django import forms
from django.utils.translation import gettext_lazy
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from pretix.base.exporter import BaseExporter
from pretix.base.models import Order
from pretix.base.timeframes import (
    DateFrameField,
    resolve_timeframe_to_datetime_start_inclusive_end_exclusive,
)

from ..renderers.order_detail_pdf_renderer import OrderDetailPDFRenderer
from ..renderers.order_detail_tabular import (
    OrderDetailCSVRenderer,
    OrderDetailExcelRenderer,
)
from ..services.order_detail_builder import OrderDetailBuilder
from ..services.recette_builder import DEFAULT_STATUSES


class OrderDetailExporter(BaseExporter):
    """One row per order, with categories and PSP fees. No personal data."""

    identifier = "order_detail_psp"
    verbose_name = gettext_lazy("Détail par commande")
    description = gettext_lazy(
        "Détail des commandes (une ligne par commande) avec catégories "
        "achetées et frais bancaires par prestataire. Sans donnée personnelle. "
        "Disponible en PDF, CSV et Excel."
    )
    category = pgettext_lazy("export_category", "Order data")
    featured = True

    @property
    def export_form_fields(self):
        return OrderedDict([
            ("date_range", DateFrameField(
                label=_("Période (date de commande)"),
                include_future_frames=False, required=False)),
            ("channel", forms.ChoiceField(
                label=_("Canal de vente"), required=False,
                choices=self._channel_choices(),
                help_text=_("Laisser vide pour inclure tous les canaux."))),
            ("status", forms.ChoiceField(
                label=_("Statut de la commande"), required=False,
                choices=(("p", _("Payées uniquement")),
                         ("pn", _("Payées et en attente"))),
                initial="p")),
            ("_format", forms.ChoiceField(
                label=_("Format d'export"),
                choices=(("pdf", "PDF"), ("csv", "CSV"), ("xlsx", "Excel")),
                initial="pdf")),
        ])

    def _channel_choices(self):
        choices = [("", _("Tous les canaux"))]
        try:
            org = self.organizer or self.events.first().organizer
            for sc in org.sales_channels.all():
                choices.append((sc.identifier, str(sc.label)))
        except Exception:
            pass
        return choices

    def render(self, form_data: dict):
        fmt = form_data.get("_format", "pdf")
        report = OrderDetailBuilder(
            list(self.events), self._builder_form_data(form_data)
        ).build()
        base = "detail-commandes"
        if fmt == "csv":
            return f"{base}.csv", "text/csv", \
                OrderDetailCSVRenderer(report).render()
        if fmt == "xlsx":
            return (
                f"{base}.xlsx",
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet",
                OrderDetailExcelRenderer(report).render(),
            )
        return f"{base}.pdf", "application/pdf", \
            OrderDetailPDFRenderer(report, self._event_meta()).render()

    def _builder_form_data(self, form_data) -> dict:
        out = {}
        if form_data.get("channel"):
            out["channel"] = form_data["channel"]
        out["statuses"] = (
            (Order.STATUS_PAID, Order.STATUS_PENDING)
            if (form_data.get("status") or "p") == "pn"
            else DEFAULT_STATUSES
        )
        rng = form_data.get("date_range")
        if rng:
            try:
                org = self.organizer or self.events.first().organizer
                start, end = \
                    resolve_timeframe_to_datetime_start_inclusive_end_exclusive(
                        org, rng)
                out["date_from"], out["date_to"] = start, end
            except Exception:
                pass
        return out

    def _event_meta(self) -> dict:
        ev = self.events.first()
        if ev is None:
            return {}
        org = self.organizer or ev.organizer
        meta = {"organizer": str(org.name) if org else "",
                "event": str(ev.name), "slug": ev.slug}
        return meta
