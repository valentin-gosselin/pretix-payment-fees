"""
"Recette Manifestation" accounting exporter (STORY-106).

Wires the builder (STORY-100..103) and the renderers (PDF / CSV / Excel,
STORY-104..105) into a Pretix BaseExporter: it appears in the event/organizer
export UI with a form (period, sales channel, format, order status) and produces
the chosen file.

This exporter is autonomous (it does NOT inherit the native ReportExporter). It
replaces the former accounting_report_psp and payment_list_psp exporters.
"""
from collections import OrderedDict

from django import forms
from django.utils.translation import gettext_lazy
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from pretix.base.exporter import BaseExporter
from pretix.base.timeframes import (
    DateFrameField,
    resolve_timeframe_to_datetime_start_inclusive_end_exclusive,
)

from ..renderers.recette_csv_renderer import RecetteCSVRenderer
from ..renderers.recette_excel_renderer import RecetteExcelRenderer
from ..renderers.recette_pdf_renderer import RecettePDFRenderer
from ..services.recette_builder import DEFAULT_STATUSES, RecetteDataBuilder

try:
    from pretix.base.models import Order
    _STATUS_CHOICES = (
        (Order.STATUS_PAID, _("Paid")),
        (Order.STATUS_PENDING, _("Pending")),
    )
except Exception:  # pragma: no cover
    _STATUS_CHOICES = ()


class RecetteManifestationExporter(BaseExporter):
    """Autonomous accounting export reproducing the Trium-style revenue report."""

    identifier = "recette_manifestation"
    verbose_name = gettext_lazy("Recettes détaillées")
    description = gettext_lazy(
        "Rapport de recettes détaillé par canal de vente et par séance, avec "
        "ventilation des frais bancaires par prestataire, recette nette, vue "
        "par séance et bloc billetterie. Disponible en PDF, CSV et Excel."
    )
    category = pgettext_lazy("export_category", "Analysis")
    featured = True

    @property
    def export_form_fields(self):
        # Labels in French (Pretix FR vocabulary). gettext_lazy keeps them
        # translatable for the other languages in STORY-106's i18n pass.
        return OrderedDict([
            ("date_range", DateFrameField(
                label=_("Période (date de commande)"),
                include_future_frames=False,
                required=False,
            )),
            ("channel", forms.ChoiceField(
                label=_("Canal de vente"),
                required=False,
                choices=self._channel_choices(),
                help_text=_("Laisser vide pour inclure tous les canaux en "
                            "sections distinctes, plus un total général."),
            )),
            ("status", forms.ChoiceField(
                label=_("Statut de la commande"),
                required=False,
                choices=(
                    ("p", _("Payées uniquement")),
                    ("pn", _("Payées et en attente")),
                ),
                initial="p",
            )),
            ("_format", forms.ChoiceField(
                label=_("Format d'export"),
                choices=(("pdf", "PDF"), ("csv", "CSV"), ("xlsx", "Excel")),
                initial="pdf",
            )),
        ])

    # -- form helpers -------------------------------------------------------

    def _channel_choices(self):
        choices = [("", _("Tous les canaux"))]
        try:
            for sc in self._organizer().sales_channels.all():
                choices.append((sc.identifier, str(sc.label)))
        except Exception:
            pass
        return choices

    def _organizer(self):
        if self.organizer:
            return self.organizer
        return self.events.first().organizer

    # -- render -------------------------------------------------------------

    def render(self, form_data: dict):
        fmt = form_data.get("_format", "pdf")
        builder_form = self._builder_form_data(form_data)
        report = RecetteDataBuilder(list(self.events), builder_form).build()

        base = "recette-manifestation"
        if fmt == "csv":
            data = RecetteCSVRenderer(report).render()
            return f"{base}.csv", "text/csv", data
        if fmt == "xlsx":
            data = RecetteExcelRenderer(report).render()
            return (
                f"{base}.xlsx",
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet",
                data,
            )
        data = RecettePDFRenderer(report, self._event_meta()).render()
        return f"{base}.pdf", "application/pdf", data

    # -- mapping form_data -> builder ---------------------------------------

    def _builder_form_data(self, form_data) -> dict:
        out = {}
        if form_data.get("channel"):
            out["channel"] = form_data["channel"]
        status = form_data.get("status") or "p"
        if status == "pn":
            out["statuses"] = (Order.STATUS_PAID, Order.STATUS_PENDING)
        else:
            out["statuses"] = DEFAULT_STATUSES
        # date range -> datetime bounds (builder filters by order date later if
        # provided; currently the builder aggregates the full event perimeter)
        rng = form_data.get("date_range")
        if rng:
            try:
                start, end = \
                    resolve_timeframe_to_datetime_start_inclusive_end_exclusive(
                        self._organizer(), rng
                    )
                out["date_from"] = start
                out["date_to"] = end
            except Exception:
                pass
        return out

    def _event_meta(self) -> dict:
        """Header metadata for the PDF, from the real event(s)."""
        ev = self.events.first()
        if ev is None:
            return {}
        org = self._organizer()
        meta = {
            "organizer": str(org.name) if org else "",
            "event": str(ev.name),
            "slug": ev.slug,
        }
        if getattr(ev, "date_from", None):
            meta["date"] = ev.date_from.strftime("%d/%m/%Y")
        loc = getattr(ev, "location", None)
        if loc:
            meta["location"] = str(loc)
        return meta
