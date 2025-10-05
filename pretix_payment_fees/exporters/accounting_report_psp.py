"""
Rapport comptable PDF avec frais PSP - Version simplifiée.

Hérite du rapport comptable natif de Pretix et ajoute uniquement
une section "Frais PSP" après la section "Paiements".
"""

import copy
from collections import defaultdict
from decimal import Decimal

from django.db.models import Sum
from django.utils.html import escape
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, pgettext_lazy
from pretix.base.models import Order, OrderFee, OrderPayment
from pretix.base.templatetags.money import money_filter
from pretix.control.forms.filter import get_all_payment_providers
from pretix.helpers.reportlab import FontFallbackParagraph
from pretix.plugins.reports.accountingreport import ReportExporter

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, Spacer, Table, TableStyle


class AccountingReportPSPExporter(ReportExporter):
    """
    Rapport comptable PDF incluant les frais PSP.

    Hérite du ReportExporter natif de Pretix et ajoute:
    - Section "Frais PSP" avec détail par provider
    - Inclusion des frais dans "Éléments ouverts"
    """

    identifier = "accounting_report_psp"
    verbose_name = gettext_lazy("Rapport comptable avec frais bancaires")
    description = gettext_lazy(
        "Rapport comptable PDF incluant le détail des frais bancaires par fournisseur de paiement (Mollie, SumUp, etc.)."
    )
    category = pgettext_lazy("export_category", "Analysis")
    filename = "accounting_report_psp"
    featured = True

    def _render_pdf(self, form_data, output_file=None):
        """
        Override de la méthode _render_pdf pour ajouter la section frais PSP.

        Copie de la structure du parent avec ajout de _table_psp_fees.
        """
        import tempfile

        from pretix.plugins.reports.exporters import ReportlabExportMixin

        from reportlab.platypus import PageTemplate

        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            ReportlabExportMixin.register_fonts()
            doc = self.get_doc_template()(
                output_file or f.name,
                pagesize=self.pagesize,
                leftMargin=10 * mm,
                rightMargin=10 * mm,
                topMargin=20 * mm,
                bottomMargin=15 * mm,
            )
            doc.addPageTemplates(
                [
                    PageTemplate(
                        id="All",
                        frames=self.get_frames(doc),
                        onPage=self.on_page,
                        pagesize=self.pagesize,
                    )
                ]
            )

            style_h1 = copy.copy(self.get_style())
            style_h1.fontName = "OpenSansBd"
            style_h1.fontSize = 14
            style_h2 = copy.copy(self.get_style())
            style_h2.fontName = "OpenSansBd"
            style_h2.fontSize = 12
            style_small = copy.copy(self.get_style())
            style_small.fontSize = 8
            style_small.leading = 10

            story = [
                FontFallbackParagraph(self.verbose_name, style_h1),
                Spacer(0, 3 * mm),
                FontFallbackParagraph(
                    "<br />".join(escape(f) for f in self.describe_filters(form_data)),
                    style_small,
                ),
            ]

            currencies = list(
                sorted(set(self.events.values_list("currency", flat=True).distinct()))
            )

            # Section Commandes (Orders)
            for c in currencies:
                c_head = f" [{c}]" if len(currencies) > 1 else ""
                story += [
                    Spacer(0, 3 * mm),
                    FontFallbackParagraph(_("Orders") + c_head, style_h2),
                    Spacer(0, 3 * mm),
                    *super()._table_transactions(form_data, c),
                ]

            # Section Paiements (Payments)
            for c in currencies:
                c_head = f" [{c}]" if len(currencies) > 1 else ""
                story += [
                    Spacer(0, 8 * mm),
                    FontFallbackParagraph(_("Payments") + c_head, style_h2),
                    Spacer(0, 3 * mm),
                    *super()._table_payments(form_data, c),
                ]

            # ➕ NOUVEAU : Section Frais PSP
            for c in currencies:
                c_head = f" [{c}]" if len(currencies) > 1 else ""
                story += [
                    Spacer(0, 8 * mm),
                    FontFallbackParagraph(_("Bank fees") + c_head, style_h2),
                    Spacer(0, 3 * mm),
                    *self._table_psp_fees(form_data, c),
                ]

            # Section Éléments ouverts (Open items)
            for c in currencies:
                c_head = f" [{c}]" if len(currencies) > 1 else ""
                story += [
                    Spacer(0, 8 * mm),
                    KeepTogether(
                        [
                            FontFallbackParagraph(_("Open items") + c_head, style_h2),
                            Spacer(0, 3 * mm),
                            *self._table_open_items(form_data, c),
                        ]
                    ),
                ]

            # Gift cards (si organizer complet)
            if self.is_multievent and self.events.count() == self.organizer.events.count():
                for c in currencies:
                    c_head = f" [{c}]" if len(currencies) > 1 else ""
                    story += [
                        Spacer(0, 8 * mm),
                        KeepTogether(
                            [
                                FontFallbackParagraph(_("Gift cards") + c_head, style_h2),
                                Spacer(0, 3 * mm),
                                *super()._table_gift_cards(form_data, c),
                            ]
                        ),
                    ]

            doc.build(story)

            if output_file:
                return self.filename + ".pdf", "application/pdf", b""
            f.seek(0)
            return self.filename + ".pdf", "application/pdf", f.read()

    def _table_psp_fees(self, form_data, currency):
        """
        Génère le tableau des frais PSP groupés par payment provider.

        Format:
        --------------------------------------------------
        Mode de paiement      | Transactions | Frais totaux
        --------------------------------------------------
        Mollie (CB)           | 73           | 44,70 €
        SumUp                 | 5            | 2,50 €
        --------------------------------------------------
        Total frais PSP       | 78           | 47,20 €
        --------------------------------------------------
        """
        tstyle = copy.copy(self.get_style())
        tstyle.fontSize = 8
        tstyle.leading = 10
        tstyle_right = copy.copy(tstyle)
        tstyle_right.alignment = TA_RIGHT
        tstyle_bold = copy.copy(tstyle)
        tstyle_bold.fontName = "OpenSansBd"
        tstyle_bold_right = copy.copy(tstyle_bold)
        tstyle_bold_right.alignment = TA_RIGHT

        # En-tête du tableau
        tdata = [
            [
                FontFallbackParagraph(_("Payment method"), tstyle_bold),
                FontFallbackParagraph(_("Transactions"), tstyle_bold_right),
                FontFallbackParagraph(_("Total fees"), tstyle_bold_right),
            ]
        ]

        # Récupérer les frais PSP
        fees_qs = (
            OrderFee.objects.filter(
                order__event__in=self.events,
                order__event__currency=currency,
                fee_type=OrderFee.FEE_TYPE_PAYMENT,
                canceled=False,
            )
            .select_related("order")
            .prefetch_related("order__payments")
        )

        # Appliquer les filtres de dates
        if form_data["date_range"]:
            from django.utils.timezone import now
            from pretix.base.timeframes import (
                resolve_timeframe_to_datetime_start_inclusive_end_exclusive,
            )

            df_start, df_end = resolve_timeframe_to_datetime_start_inclusive_end_exclusive(
                now(), form_data["date_range"], self.timezone
            )
            if df_start:
                fees_qs = fees_qs.filter(order__datetime__gte=df_start)
            if df_end:
                fees_qs = fees_qs.filter(order__datetime__lt=df_end)

        if form_data["no_testmode"]:
            fees_qs = fees_qs.filter(order__testmode=False)

        # Grouper par provider
        fees_by_provider = defaultdict(lambda: {"count": 0, "total": Decimal("0")})

        for fee in fees_qs:
            # Trouver le payment provider associé
            payment = (
                fee.order.payments.filter(state=OrderPayment.PAYMENT_STATE_CONFIRMED)
                .order_by("-payment_date")
                .first()
            )

            if payment:
                provider = payment.provider
                fees_by_provider[provider]["count"] += 1
                fees_by_provider[provider]["total"] += fee.value

        # Récupérer les noms des providers
        provider_names = dict(get_all_payment_providers())

        # Construire les lignes du tableau
        tstyledata = []
        providers_sorted = sorted(fees_by_provider.keys())

        for provider in providers_sorted:
            data = fees_by_provider[provider]
            tdata.append(
                [
                    Paragraph(provider_names.get(provider, provider), tstyle),
                    Paragraph(str(data["count"]), tstyle_right),
                    Paragraph(money_filter(data["total"], currency), tstyle_right),
                ]
            )

        # Ligne totale
        total_count = sum(f["count"] for f in fees_by_provider.values())
        total_fees = sum(f["total"] for f in fees_by_provider.values())

        tdata.append(
            [
                FontFallbackParagraph(_("Total frais bancaires"), tstyle_bold),
                Paragraph(str(total_count), tstyle_bold_right),
                Paragraph(money_filter(total_fees, currency), tstyle_bold_right),
            ]
        )

        # Style du tableau
        tstyledata += [
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
            ("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (0, -1), 0),
            ("RIGHTPADDING", (-1, 0), (-1, -1), 0),
        ]

        colwidths = [a * (self.pagesize[0] - 20 * mm) for a in [0.60, 0.20, 0.20]]
        table = Table(tdata, colWidths=colwidths, repeatRows=1)
        table.setStyle(TableStyle(tstyledata))

        return [table]

    def _table_open_items(self, form_data, currency):
        """
        Override de _table_open_items pour inclure les frais PSP dans le calcul.

        Clone de la méthode parent avec ajout d'une ligne "Frais PSP".
        """
        import datetime

        from django.db.models import F
        from django.utils.formats import date_format
        from django.utils.timezone import now
        from pretix.base.timeframes import (
            resolve_timeframe_to_datetime_start_inclusive_end_exclusive,
        )

        tstyle = copy.copy(self.get_style())
        tstyle.fontSize = 8
        tstyle.leading = 10
        tstyle_right = copy.copy(tstyle)
        tstyle_right.alignment = TA_RIGHT
        tstyle_bold = copy.copy(tstyle)
        tstyle_bold.fontName = "OpenSansBd"
        tstyle_bold_right = copy.copy(tstyle_bold)
        tstyle_bold_right.alignment = TA_RIGHT

        if form_data.get("date_range"):
            df_start, df_end = resolve_timeframe_to_datetime_start_inclusive_end_exclusive(
                now(), form_data["date_range"], self.timezone
            )
        else:
            df_start = df_end = None

        tstyledata = []
        tdata = []

        # Calcul initial si date de début
        if df_start:
            tx_before = self._transaction_qs(form_data, currency, ignore_dates=True).filter(
                datetime__lt=df_start
            ).aggregate(s=Sum(F("count") * F("price")))["s"] or Decimal("0.00")
            p_before = self._payment_qs(form_data, currency, ignore_dates=True).filter(
                payment_date__lt=df_start
            ).aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
            r_before = self._refund_qs(form_data, currency, ignore_dates=True).filter(
                execution_date__lt=df_start
            ).aggregate(s=Sum("amount"))["s"] or Decimal("0.00")

            open_before = tx_before - p_before + r_before

            tdata.append(
                [
                    FontFallbackParagraph(
                        _("Pending payments at {datetime}").format(
                            datetime=date_format(
                                df_start - datetime.timedelta.resolution,
                                "SHORT_DATETIME_FORMAT",
                            )
                        ),
                        tstyle,
                    ),
                    Paragraph(money_filter(open_before, currency), tstyle_right),
                ]
            )

        # Transactions de la période
        tx_total = self._transaction_qs(form_data, currency).aggregate(
            s=Sum(F("count") * F("price"))
        )["s"] or Decimal("0.00")
        tdata.append(
            [
                FontFallbackParagraph(_("Orders"), tstyle),
                Paragraph("+" + money_filter(tx_total, currency), tstyle_right),
            ]
        )

        # Paiements avec sous-lignes pour les frais
        p_total = self._payment_qs(form_data, currency).aggregate(s=Sum("amount"))["s"] or Decimal(
            "0.00"
        )
        tdata.append(
            [
                FontFallbackParagraph(_("Payments"), tstyle),
                Paragraph("-" + money_filter(p_total, currency), tstyle_right),
            ]
        )

        # Calculer les frais PSP de la période
        fees_total = OrderFee.objects.filter(
            order__event__in=self.events,
            order__event__currency=currency,
            fee_type=OrderFee.FEE_TYPE_PAYMENT,
            canceled=False,
        )

        if form_data["date_range"]:
            if df_start:
                fees_total = fees_total.filter(order__datetime__gte=df_start)
            if df_end:
                fees_total = fees_total.filter(order__datetime__lt=df_end)

        if form_data["no_testmode"]:
            fees_total = fees_total.filter(order__testmode=False)

        fees_total = fees_total.aggregate(s=Sum("value"))["s"] or Decimal("0.00")

        # Ajouter les sous-lignes pour les frais bancaires si présents
        if fees_total > 0:
            # Style indenté pour les sous-lignes
            tstyle_indent = copy.copy(tstyle)
            tstyle_indent.leftIndent = 15

            # Sous-ligne : Frais bancaires
            tdata.append(
                [
                    FontFallbackParagraph("  - " + _("Bank fees"), tstyle_indent),
                    Paragraph("-" + money_filter(fees_total, currency), tstyle_right),
                ]
            )

            # Sous-ligne : Total net perçu
            net_received = p_total - fees_total
            tdata.append(
                [
                    FontFallbackParagraph("  - " + _("Total net received"), tstyle_indent),
                    Paragraph("-" + money_filter(net_received, currency), tstyle_right),
                ]
            )

        # Remboursements
        r_total = self._refund_qs(form_data, currency).aggregate(s=Sum("amount"))["s"] or Decimal(
            "0.00"
        )
        tdata.append(
            [
                FontFallbackParagraph(_("Refunds"), tstyle),
                Paragraph("+" + money_filter(r_total, currency), tstyle_right),
            ]
        )

        # Total final (sans soustraire les frais)
        if df_start:
            final_balance = open_before + tx_total - p_total + r_total
        else:
            final_balance = tx_total - p_total + r_total

        tdata.append(
            [
                FontFallbackParagraph(
                    _("Pending payments at {datetime}").format(
                        datetime=date_format(now(), "SHORT_DATETIME_FORMAT")
                    ),
                    tstyle_bold,
                ),
                Paragraph("=" + money_filter(final_balance, currency), tstyle_bold_right),
            ]
        )

        tstyledata += [
            ("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (0, -1), 0),
            ("RIGHTPADDING", (-1, 0), (-1, -1), 0),
        ]

        colwidths = [a * (self.pagesize[0] - 20 * mm) for a in [0.7, 0.3]]
        table = Table(tdata, colWidths=colwidths, repeatRows=1)
        table.setStyle(TableStyle(tstyledata))

        return [table]
