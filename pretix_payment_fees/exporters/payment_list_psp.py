"""
Export des paiements et remboursements avec frais bancaires PSP.

Étend l'export natif de Pretix en ajoutant les colonnes des frais bancaires
pour chaque paiement (Mollie, SumUp, etc.).
"""

from collections import OrderedDict
from decimal import Decimal
from zoneinfo import ZoneInfo

from django import forms
from django.utils.timezone import now
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, pgettext_lazy
from pretix.base.exporter import ListExporter
from pretix.base.models.orders import OrderFee, OrderPayment, OrderRefund
from pretix.base.timeframes import (
    DateFrameField,
    resolve_timeframe_to_datetime_start_inclusive_end_exclusive,
)
from pretix.control.forms.filter import get_all_payment_providers


class PaymentListPSPExporter(ListExporter):
    """
    Export des paiements et remboursements avec détail des frais bancaires PSP.

    Ajoute 3 colonnes supplémentaires à l'export standard :
    - Frais bancaires : montant des frais PSP
    - Fournisseur frais : Mollie, SumUp, etc.
    - Type frais : carte crédit, Bancontact, etc.
    """

    identifier = "payment_list_psp"
    verbose_name = gettext_lazy("Paiements et remboursements avec frais bancaires")
    description = gettext_lazy(
        "Export des paiements et remboursements incluant le détail des frais bancaires PSP (Mollie, SumUp, etc.)."
    )
    category = pgettext_lazy("export_category", "Order data")
    filename = "payment_list_psp"
    featured = True

    @property
    def additional_form_fields(self):
        return OrderedDict(
            [
                ("end_date_range",
                 DateFrameField(
                     label=_("Date range (payment date)"),
                     include_future_frames=False,
                     required=False,
                     help_text=_("Note that using this will exclude any non-confirmed payments or non-completed refunds."),
                 ),
                 ),
                ("start_date_range",
                 DateFrameField(
                     label=_("Date range (start of transaction)"),
                     include_future_frames=False,
                     required=False,
                 ),
                 ),
                ("payment_states",
                 forms.MultipleChoiceField(
                     label=_("Payment states"),
                     choices=OrderPayment.PAYMENT_STATES,
                     initial=[
                         OrderPayment.PAYMENT_STATE_CONFIRMED,
                         OrderPayment.PAYMENT_STATE_REFUNDED,
                     ],
                     required=False,
                     widget=forms.CheckboxSelectMultiple,
                 ),
                 ),
                ("refund_states",
                 forms.MultipleChoiceField(
                     label=_("Refund states"),
                     choices=OrderRefund.REFUND_STATES,
                     initial=[
                         OrderRefund.REFUND_STATE_DONE,
                         OrderRefund.REFUND_STATE_CREATED,
                         OrderRefund.REFUND_STATE_TRANSIT,
                     ],
                     widget=forms.CheckboxSelectMultiple,
                     required=False,
                 ),
                 ),
            ])

    def iterate_list(self, form_data):
        provider_names = dict(get_all_payment_providers())

        # Mapper les types internes vers des noms lisibles
        fee_type_names = {
            "mollie_fee": _("Frais Mollie"),
            "mollie_oauth_fee": _("Frais Mollie"),
            "mollie_creditcard_fee": _("Credit card"),
            "mollie_bancontact_fee": _("Bancontact"),
            "mollie_ideal_fee": _("iDEAL"),
            "sumup_fee": _("Frais SumUp"),
        }

        payments = (
            OrderPayment.objects.filter(
                order__event__in=self.events, state__in=form_data.get("payment_states", [])
            )
            .select_related("order")
            .prefetch_related("order__event")
            .order_by("created")
        )

        refunds = (
            OrderRefund.objects.filter(
                order__event__in=self.events, state__in=form_data.get("refund_states", [])
            )
            .select_related("order")
            .prefetch_related("order__event")
            .order_by("created")
        )

        if form_data.get("end_date_range"):
            dt_start, dt_end = resolve_timeframe_to_datetime_start_inclusive_end_exclusive(
                now(), form_data["end_date_range"], self.timezone
            )
            if dt_start:
                payments = payments.filter(payment_date__gte=dt_start)
                refunds = refunds.filter(execution_date__gte=dt_start)
            if dt_end:
                payments = payments.filter(payment_date__lt=dt_end)
                refunds = refunds.filter(execution_date__lt=dt_end)

        if form_data.get("start_date_range"):
            dt_start, dt_end = resolve_timeframe_to_datetime_start_inclusive_end_exclusive(
                now(), form_data["start_date_range"], self.timezone
            )
            if dt_start:
                payments = payments.filter(created__gte=dt_start)
                refunds = refunds.filter(created__gte=dt_start)
            if dt_end:
                payments = payments.filter(created__lt=dt_end)
                refunds = refunds.filter(created__lt=dt_end)

        objs = sorted(list(payments) + list(refunds), key=lambda o: o.created)

        # Headers avec les nouvelles colonnes pour les frais
        headers = [
            _("Event slug"),
            _("Order"),
            _("Payment ID"),
            _("Creation date"),
            _("Completion date"),
            _("Status"),
            _("Status code"),
            _("Amount"),
            _("Payment method"),
            _("Comment"),
            _("Matching ID"),
            _("Payment details"),
            _("Bank fees"),
            _("Fournisseur frais"),
            _("Type frais"),
        ]
        yield headers

        yield self.ProgressSetTotal(total=len(objs))

        for obj in objs:
            tz = ZoneInfo(obj.order.event.settings.timezone)

            # Date de complétion
            if isinstance(obj, OrderPayment) and obj.payment_date:
                d2 = obj.payment_date.astimezone(tz).date().strftime("%Y-%m-%d")
            elif isinstance(obj, OrderRefund) and obj.execution_date:
                d2 = obj.execution_date.astimezone(tz).date().strftime("%Y-%m-%d")
            else:
                d2 = ""

            # Matching ID et détails de paiement
            matching_id = ""
            payment_details = ""
            try:
                if isinstance(obj, OrderPayment):
                    matching_id = obj.payment_provider.matching_id(obj) or ""
                    payment_details = obj.payment_provider.payment_control_render_short(obj)
                elif isinstance(obj, OrderRefund):
                    matching_id = obj.payment_provider.refund_matching_id(obj) or ""
                    payment_details = obj.payment_provider.refund_control_render_short(obj)
            except Exception:
                pass

            # Récupération des frais PSP pour ce paiement
            fee_amount = Decimal("0.00")
            fee_provider = ""
            fee_type = ""

            if isinstance(obj, OrderPayment):
                # Rechercher les frais PSP associés à cette commande
                fees = OrderFee.objects.filter(
                    order=obj.order, fee_type=OrderFee.FEE_TYPE_PAYMENT, canceled=False
                )

                # Filtrer par provider si possible
                if obj.provider in [
                    "mollie",
                    "mollie_bancontact",
                    "mollie_ideal",
                    "mollie_creditcard",
                ]:
                    fees = fees.filter(internal_type__startswith="mollie")
                elif obj.provider == "sumup":
                    fees = fees.filter(internal_type__startswith="sumup")

                # Prendre le premier frais trouvé (normalement il n'y en a qu'un par paiement)
                if fees.exists():
                    fee = fees.first()
                    fee_amount = fee.value

                    # Déterminer le fournisseur
                    if fee.internal_type and fee.internal_type.startswith("mollie"):
                        fee_provider = "Mollie"
                    elif fee.internal_type and fee.internal_type.startswith("sumup"):
                        fee_provider = "SumUp"
                    else:
                        fee_provider = fee.internal_type or ""

                    # Type de frais
                    fee_type = fee_type_names.get(fee.internal_type, fee.internal_type or "")

            row = [
                obj.order.event.slug,
                obj.order.code,
                obj.full_id,
                obj.created.astimezone(tz).date().strftime("%Y-%m-%d"),
                d2,
                obj.get_state_display(),
                obj.state,
                obj.amount * (-1 if isinstance(obj, OrderRefund) else 1),
                provider_names.get(obj.provider, obj.provider),
                obj.comment if isinstance(obj, OrderRefund) else "",
                matching_id,
                payment_details,
                fee_amount if fee_amount > 0 else "",
                fee_provider,
                fee_type,
            ]
            yield row
