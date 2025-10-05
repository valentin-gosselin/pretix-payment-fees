import logging
from datetime import timedelta

from django.contrib import messages
from django.db.models import Count, Sum
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, TemplateView
from pretix.base.models import Event, OrderPayment
from pretix.control.permissions import OrganizerPermissionRequiredMixin

from .forms import PSPAutoSyncForm, PSPSyncForm
from .models import PSPConfig, PSPTransactionCache
from .services.psp_sync import PSPSyncService

logger = logging.getLogger(__name__)


class DiagnosticView(OrganizerPermissionRequiredMixin, TemplateView):
    """Diagnostic view for the plugin."""

    template_name = "pretix_payment_fees/diagnostic.html"
    permission = "can_change_organizer_settings"

    def get_context_data(self, **kwargs):
        """Add diagnostic data."""
        ctx = super().get_context_data(**kwargs)
        ctx["organizer"] = self.request.organizer

        # PSP configuration
        try:
            psp_config = PSPConfig.objects.get(organizer=self.request.organizer)
            ctx["psp_config"] = psp_config
            ctx["has_config"] = True
        except PSPConfig.DoesNotExist:
            ctx["psp_config"] = None
            ctx["has_config"] = False

        # Cache statistics
        cache_stats = self._get_cache_stats()
        ctx["cache_stats"] = cache_stats

        # Recent events
        ctx["recent_errors"] = self._get_recent_errors()

        return ctx

    def _get_cache_stats(self):
        """Retrieve cache statistics."""
        organizer = self.request.organizer
        now_time = now()

        # Total transactions en cache
        total_cached = PSPTransactionCache.objects.filter(organizer=organizer).count()

        # Par provider
        by_provider = (
            PSPTransactionCache.objects.filter(organizer=organizer)
            .values("psp_provider")
            .annotate(
                count=Count("id"),
                total_fees=Sum("amount_fee"),
                total_gross=Sum("amount_gross"),
            )
        )

        # Cache récent (dernière heure)
        recent_cached = PSPTransactionCache.objects.filter(
            organizer=organizer, created__gte=now_time - timedelta(hours=1)
        ).count()

        # Cache ancien (> 24h)
        old_cached = PSPTransactionCache.objects.filter(
            organizer=organizer, modified__lt=now_time - timedelta(hours=24)
        ).count()

        return {
            "total": total_cached,
            "by_provider": list(by_provider),
            "recent": recent_cached,
            "old": old_cached,
        }

    def _get_recent_errors(self):
        """
        Retrieve recent API errors from Django logs.

        Returns:
            list: Recent errors from the last 24 hours, limited to 10 entries
        """
        from django.contrib.admin.models import LogEntry, CHANGE
        from django.utils.timezone import now
        from datetime import timedelta

        # Get error logs from the last 24 hours for this organizer
        yesterday = now() - timedelta(days=1)

        # Query LogEntry for PSP-related errors
        error_logs = LogEntry.objects.filter(
            content_type__app_label='pretix_payment_fees',
            action_time__gte=yesterday,
            action_flag=CHANGE,
            change_message__icontains='error'
        ).order_by('-action_time')[:10]

        # Format errors for display
        errors = []
        for log in error_logs:
            errors.append({
                'timestamp': log.action_time,
                'message': log.change_message,
                'user': log.user.email if log.user else 'System'
            })

        return errors


class PSPSyncView(OrganizerPermissionRequiredMixin, FormView):
    """View for manual PSP fee synchronization."""

    template_name = "pretix_payment_fees/psp_sync.html"
    permission = "can_change_organizer_settings"
    form_class = PSPSyncForm

    def get_form_kwargs(self):
        """Pass organizer to form."""
        kwargs = super().get_form_kwargs()
        kwargs["organizer"] = self.request.organizer
        return kwargs

    def get_context_data(self, **kwargs):
        """Add context data."""
        ctx = super().get_context_data(**kwargs)
        ctx["organizer"] = self.request.organizer

        # PSP configuration
        try:
            psp_config = PSPConfig.objects.get(organizer=self.request.organizer)
            ctx["psp_config"] = psp_config
            ctx["has_config"] = True
            ctx["mollie_enabled"] = psp_config.mollie_enabled and psp_config.mollie_api_key
            ctx["sumup_enabled"] = psp_config.sumup_enabled and psp_config.sumup_api_key

            # Auto-sync form
            if 'auto_sync_form' not in ctx:
                ctx["auto_sync_form"] = PSPAutoSyncForm(instance=psp_config)
        except PSPConfig.DoesNotExist:
            ctx["psp_config"] = None
            ctx["has_config"] = False
            ctx["mollie_enabled"] = False
            ctx["sumup_enabled"] = False
            ctx["auto_sync_form"] = None

        # Unsynchronized payment statistics
        ctx["pending_stats"] = self._get_pending_stats()

        return ctx

    def _get_pending_stats(self):
        """Retrieve unsynchronized payment statistics."""
        from pretix.base.models import OrderFee

        organizer = self.request.organizer

        # Paiements confirmés
        all_payments = OrderPayment.objects.filter(
            order__event__organizer=organizer,
            state=OrderPayment.PAYMENT_STATE_CONFIRMED,
            provider__in=["mollie", "mollie_bancontact", "mollie_ideal", "mollie_creditcard", "sumup"]
        ).select_related('order')

        total_pending = 0
        by_provider = {}

        for payment in all_payments:
            # Vérifier si un OrderFee de type payment existe pour ce paiement
            # On cherche un fee avec le provider correspondant (ex: mollie_creditcard_fee)
            provider_fee_type = f"{payment.provider}_fee"
            has_fee = OrderFee.objects.filter(
                order=payment.order,
                fee_type=OrderFee.FEE_TYPE_PAYMENT,
                internal_type=provider_fee_type
            ).exists()

            if not has_fee:
                total_pending += 1
                provider = payment.provider
                by_provider[provider] = by_provider.get(provider, 0) + 1

        return {
            "total": total_pending,
            "by_provider": by_provider,
        }

    def post(self, request, *args, **kwargs):
        """Handle both forms: manual sync and auto-sync."""
        # Vérifier quel formulaire a été soumis
        if 'save_auto_sync' in request.POST:
            # Auto-sync form
            try:
                psp_config = PSPConfig.objects.get(organizer=request.organizer)
                auto_sync_form = PSPAutoSyncForm(request.POST, instance=psp_config)

                if auto_sync_form.is_valid():
                    auto_sync_form.save()
                    messages.success(
                        request,
                        _("Automatic synchronization configuration has been saved."),
                    )
                    return redirect(
                        reverse(
                            "plugins:pretix_payment_fees:psp_sync",
                            kwargs={"organizer": request.organizer.slug},
                        )
                    )
                else:
                    # Retourner avec les erreurs
                    ctx = self.get_context_data()
                    ctx['auto_sync_form'] = auto_sync_form
                    return self.render_to_response(ctx)
            except PSPConfig.DoesNotExist:
                messages.error(request, _("PSP configuration not found."))
                return redirect(
                    reverse(
                        "plugins:pretix_payment_fees:settings",
                        kwargs={"organizer": request.organizer.slug},
                    )
                )
        else:
            # Formulaire de synchronisation manuelle
            return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        """Process form and start synchronization."""
        # Récupérer les paramètres
        event_slug = form.cleaned_data.get("event")
        date_from = form.cleaned_data.get("date_from")
        date_to = form.cleaned_data.get("date_to")
        days_back = form.cleaned_data.get("days_back")
        force = form.cleaned_data.get("force", False)
        dry_run = form.cleaned_data.get("dry_run", False)

        # Afficher un message de traitement en cours
        if not dry_run:
            messages.info(
                self.request,
                _("Processing your request... Synchronization may take several minutes for a large number of payments."),
            )

        try:
            # Initialiser le service
            sync_service = PSPSyncService(organizer=self.request.organizer)

            # Synchroniser
            if event_slug:
                event = Event.objects.get(
                    slug=event_slug, organizer=self.request.organizer
                )
                result = sync_service.sync_event_payments(
                    event=event,
                    date_from=date_from,
                    date_to=date_to,
                    days_back=days_back,
                    force=force,
                    dry_run=dry_run,
                )
            else:
                # Synchroniser TOUS les paiements (sans limite)
                # L'utilisateur peut limiter lui-même avec les dates si nécessaire
                result = sync_service.sync_organizer_payments(
                    date_from=date_from,
                    date_to=date_to,
                    days_back=days_back,
                    force=force,
                    dry_run=dry_run,
                    max_payments=None,  # No limit
                )

            # Afficher les résultats
            if dry_run:
                messages.info(
                    self.request,
                    _(
                        "Mode dry-run: {synced} paiements seraient synchronisés "
                        "(total frais: {fees} EUR)"
                    ).format(synced=result.synced_payments, fees=result.total_fees),
                )
            else:
                messages.success(
                    self.request,
                    _(
                        "Synchronisation réussie: {synced}/{total} paiements synchronisés, "
                        "{skipped} ignorés, {failed} échoués. Total frais: {fees} EUR"
                    ).format(
                        synced=result.synced_payments,
                        total=result.total_payments,
                        skipped=result.skipped_payments,
                        failed=result.failed_payments,
                        fees=result.total_fees,
                    ),
                )

            # Afficher les erreurs
            if result.errors:
                for error in result.errors[:5]:  # Limiter à 5 erreurs affichées
                    messages.error(
                        self.request,
                        _("Payment error {payment_id}: {error}").format(
                            payment_id=error["payment_id"], error=error["error"]
                        ),
                    )
                if len(result.errors) > 5:
                    messages.warning(
                        self.request,
                        _("... and {count} other errors").format(
                            count=len(result.errors) - 5
                        ),
                    )

        except Exception as e:
            logger.exception("Error during PSP synchronization")
            messages.error(
                self.request,
                _("Error during synchronization: {error}").format(error=str(e)),
            )

        return redirect(
            reverse(
                "plugins:pretix_payment_fees:psp_sync",
                kwargs={"organizer": self.request.organizer.slug},
            )
        )