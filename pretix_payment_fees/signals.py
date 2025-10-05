# Signal receivers for Export Frais plugin
import logging

from django.dispatch import receiver
from django.urls import include, path, resolve, reverse
from django.utils.translation import gettext_lazy as _
from pretix.base.signals import (
    order_fee_type_name,
    order_paid,
    periodic_task,
    register_data_exporters,
    register_multievent_data_exporters,
)
from pretix.control.signals import nav_organizer
from pretix.multidomain.urlreverse import get_event_domain

logger = logging.getLogger(__name__)


@receiver(register_data_exporters, dispatch_uid="accounting_report_psp")
def register_accounting_psp_report(sender, **kwargs):
    from .exporters.accounting_report_psp import AccountingReportPSPExporter

    return AccountingReportPSPExporter


@receiver(register_multievent_data_exporters, dispatch_uid="accounting_report_psp_multi")
def register_accounting_psp_report_multi(sender, **kwargs):
    from .exporters.accounting_report_psp import AccountingReportPSPExporter

    return AccountingReportPSPExporter


@receiver(register_data_exporters, dispatch_uid="payment_list_psp")
def register_payment_list_psp(sender, **kwargs):
    from .exporters.payment_list_psp import PaymentListPSPExporter

    return PaymentListPSPExporter


@receiver(register_multievent_data_exporters, dispatch_uid="payment_list_psp_multi")
def register_payment_list_psp_multi(sender, **kwargs):
    from .exporters.payment_list_psp import PaymentListPSPExporter

    return PaymentListPSPExporter


@receiver(nav_organizer, dispatch_uid="payment_fees_nav_organizer")
def navbar_organizer(sender, request, organizer, **kwargs):
    """Ajoute un lien dans les paramètres de l'organisateur pour la gestion des frais bancaires."""
    url = resolve(request.path_info)
    if not request.user.has_organizer_permission(
        organizer, "can_change_organizer_settings", request
    ):
        return []
    return [
        {
            "label": _("Bank fees"),
            "url": reverse(
                "plugins:pretix_payment_fees:settings",
                kwargs={"organizer": organizer.slug},
            ),
            "active": url.namespace == "plugins:pretix_payment_fees" and url.url_name == "settings",
            "icon": "credit-card",
        },
    ]


@receiver(order_fee_type_name, dispatch_uid="payment_fees_fee_type_name")
def get_fee_type_name(sender, fee_type, internal_type, **kwargs):
    """
    Retourne un nom lisible pour les frais PSP dans l'interface Pretix.

    Args:
        sender: L'événement
        fee_type: Le type de frais (ex: "payment")
        internal_type: Le type interne (ex: "mollie_creditcard_fee")

    Returns:
        str: Nom lisible du type de frais, ou None si non géré par ce plugin
    """
    # Mapper les types internes vers des noms lisibles
    fee_names = {
        "mollie_fee": _("Mollie fees"),
        "mollie_oauth_fee": _("Mollie fees"),
        "mollie_creditcard_fee": _("Mollie fees (Credit card)"),
        "mollie_bancontact_fee": _("Mollie fees (Bancontact)"),
        "mollie_ideal_fee": _("Mollie fees (iDEAL)"),
        "sumup_fee": _("SumUp fees"),
    }

    return fee_names.get(internal_type)


@receiver(order_paid, dispatch_uid="export_frais_order_paid")
def on_order_paid(sender, **kwargs):
    """
    Synchronise automatiquement les frais PSP quand une commande est payée.

    Ce signal est déclenché par Pretix quand une commande passe à l'état payé.
    On récupère le dernier paiement confirmé et on synchronise ses frais PSP.
    """
    order = sender

    # Vérifier qu'on a une configuration PSP
    from .models import PSPConfig
    from .services.psp_sync import PSPSyncService

    try:
        psp_config = PSPConfig.objects.get(organizer=order.event.organizer)
    except PSPConfig.DoesNotExist:
        logger.debug(
            f"No PSP config for organizer {order.event.organizer.slug}, skipping auto-sync"
        )
        return

    # Vérifier qu'au moins un PSP est activé
    if not (psp_config.mollie_enabled or psp_config.sumup_enabled):
        logger.debug(
            f"No PSP enabled for organizer {order.event.organizer.slug}, skipping auto-sync"
        )
        return

    # Récupérer le dernier paiement confirmé
    from pretix.base.models import OrderPayment

    payment = (
        order.payments.filter(state=OrderPayment.PAYMENT_STATE_CONFIRMED)
        .order_by("-payment_date")
        .first()
    )

    if not payment:
        logger.warning(f"Order {order.code} marked as paid but no confirmed payment found")
        return

    # Vérifier si le provider est supporté
    supported_providers = [
        "mollie",
        "mollie_bancontact",
        "mollie_ideal",
        "mollie_creditcard",
        "sumup",
    ]
    if payment.provider not in supported_providers:
        logger.debug(f"Payment provider {payment.provider} not supported for auto-sync, skipping")
        return

    # Synchroniser automatiquement les frais
    logger.info(f"Auto-syncing PSP fees for order {order.code}, payment {payment.id}")

    try:
        sync_service = PSPSyncService(organizer=order.event.organizer, psp_config=psp_config)
        result = sync_service.sync_payments([payment], force=False, dry_run=False)

        if result.synced_payments > 0:
            logger.info(
                f"Successfully auto-synced PSP fees for order {order.code}: {result.total_fees} EUR"
            )
        elif result.skipped_payments > 0:
            logger.debug(
                f"Payment {payment.id} skipped during auto-sync (already synced or zero fees)"
            )
        else:
            logger.warning(f"Failed to auto-sync PSP fees for order {order.code}: {result.errors}")
    except Exception as e:
        logger.error(f"Error during auto-sync for order {order.code}: {e}", exc_info=True)


@receiver(periodic_task, dispatch_uid="payment_fees_auto_sync")
def auto_sync_payment_fees(sender, **kwargs):
    """
    Synchronisation automatique périodique des frais PSP.

    Cette tâche est exécutée par le système de tâches périodiques de Pretix (runperiodic).
    Elle synchronise automatiquement les nouveaux paiements pour tous les organisateurs
    qui ont activé la synchronisation automatique.
    """
    from datetime import timedelta

    from django.utils.timezone import now
    from pretix.base.models import OrderPayment, Organizer

    from .models import PSPConfig
    from .services.psp_sync import PSPSyncService

    logger.info("Running periodic auto-sync for payment fees")

    # Parcourir tous les organisateurs avec auto_sync activé
    configs = PSPConfig.objects.filter(auto_sync_enabled=True).select_related("organizer")

    for psp_config in configs:
        try:
            # Vérifier si au moins un PSP est activé
            if not (psp_config.mollie_enabled or psp_config.sumup_enabled):
                logger.debug(f"Skipping {psp_config.organizer.slug}: no PSP enabled")
                continue

            # Déterminer si on doit synchroniser selon l'intervalle configuré
            should_sync = False
            interval_hours = {
                "hourly": 1,
                "6hours": 6,
                "daily": 24,
            }

            hours_since_last_sync = interval_hours.get(psp_config.auto_sync_interval, 6)

            if not psp_config.last_auto_sync:
                # Première synchronisation
                should_sync = True
                logger.info(f"First auto-sync for {psp_config.organizer.slug}")
            else:
                time_since_last = now() - psp_config.last_auto_sync
                if time_since_last >= timedelta(hours=hours_since_last_sync):
                    should_sync = True
                    logger.info(
                        f"Auto-sync due for {psp_config.organizer.slug} (last: {psp_config.last_auto_sync})"
                    )

            if not should_sync:
                logger.debug(f"Skipping {psp_config.organizer.slug}: too soon since last sync")
                continue

            # Récupérer les paiements des 30 derniers jours
            # On doit utiliser le scope pour l'organizer
            from django_scopes import scope

            with scope(organizer=psp_config.organizer):
                date_from = now() - timedelta(days=30)
                payments = OrderPayment.objects.filter(
                    order__event__organizer=psp_config.organizer,
                    state=OrderPayment.PAYMENT_STATE_CONFIRMED,
                    provider__in=[
                        "mollie",
                        "mollie_bancontact",
                        "mollie_ideal",
                        "mollie_creditcard",
                        "sumup",
                    ],
                    payment_date__gte=date_from,
                ).select_related("order", "order__event")

                logger.info(
                    f"Auto-syncing {payments.count()} payments for {psp_config.organizer.slug}"
                )

                # Lancer la synchronisation avec skip_already_synced=True (optimisation)
                sync_service = PSPSyncService(organizer=psp_config.organizer, psp_config=psp_config)
                result = sync_service.sync_payments(
                    payments,
                    force=False,
                    dry_run=False,
                    skip_already_synced=True,  # Ne synchronise que les nouveaux
                )

                # Mettre à jour le timestamp
                psp_config.last_auto_sync = now()
                psp_config.save(update_fields=["last_auto_sync"])

            logger.info(
                f"Auto-sync completed for {psp_config.organizer.slug}: "
                f"{result.synced_payments} synced, {result.skipped_payments} skipped, "
                f"{result.failed_payments} failed, total fees: {result.total_fees} EUR"
            )

        except Exception as e:
            logger.error(
                f"Error during auto-sync for {psp_config.organizer.slug}: {e}", exc_info=True
            )
