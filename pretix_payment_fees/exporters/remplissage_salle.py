"""
"Remplissage de salle" exporter (STORY-202).

Venue occupancy for partners: ticket counts per category + quota fill rate.
No monetary value. PDF / CSV / Excel.
"""
from collections import OrderedDict

from django import forms
from django.utils.translation import gettext_lazy
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from pretix.base.exporter import BaseExporter
from pretix.base.models import Order
from pretix.base.timeframes import DateFrameField

from ..renderers.remplissage_pdf_renderer import RemplissagePDFRenderer
from ..renderers.remplissage_tabular import (
    RemplissageCSVRenderer,
    RemplissageExcelRenderer,
)
from ..services.recette_builder import DEFAULT_STATUSES
from ..services.remplissage_builder import RemplissageBuilder


class RemplissageSalleExporter(BaseExporter):
    """Ticket counts per category + quota fill rate. No monetary value."""

    identifier = "remplissage_salle"
    verbose_name = gettext_lazy("Remplissage de salle")
    description = gettext_lazy(
        "État de remplissage de la salle pour les partenaires : nombre de "
        "places par catégorie et taux de remplissage par quota. Aucune valeur "
        "financière. Disponible en PDF, CSV et Excel."
    )
    category = pgettext_lazy("export_category", "Analysis")
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
        builder_form = {}
        if form_data.get("channel"):
            builder_form["channel"] = form_data["channel"]
        builder_form["statuses"] = DEFAULT_STATUSES
        report = RemplissageBuilder(list(self.events), builder_form).build()
        base = "remplissage-salle"
        if fmt == "csv":
            return f"{base}.csv", "text/csv", \
                RemplissageCSVRenderer(report).render()
        if fmt == "xlsx":
            return (
                f"{base}.xlsx",
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet",
                RemplissageExcelRenderer(report).render(),
            )
        return f"{base}.pdf", "application/pdf", \
            RemplissagePDFRenderer(report, self._event_meta()).render()

    def _event_meta(self) -> dict:
        ev = self.events.first()
        if ev is None:
            return {}
        org = self.organizer or ev.organizer
        meta = {"organizer": str(org.name) if org else "",
                "event": str(ev.name), "slug": ev.slug}
        if getattr(ev, "date_from", None):
            meta["date"] = ev.date_from.strftime("%d/%m/%Y")
        return meta
