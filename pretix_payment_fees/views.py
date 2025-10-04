import logging

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView
from pretix.control.permissions import OrganizerPermissionRequiredMixin

from .forms import PSPConfigForm
from .models import PSPConfig

logger = logging.getLogger(__name__)


class PSPConfigView(OrganizerPermissionRequiredMixin, FormView):
    """Vue de configuration des PSP au niveau organisateur."""

    template_name = "pretix_payment_fees/settings.html"
    form_class = PSPConfigForm
    permission = "can_change_organizer_settings"

    def get_object(self):
        """Récupère ou crée la configuration PSP."""
        config, created = PSPConfig.objects.get_or_create(organizer=self.request.organizer)
        return config

    def get_form_kwargs(self):
        """Passe l'instance au formulaire."""
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = self.get_object()
        return kwargs

    def form_valid(self, form):
        """Sauvegarde la configuration."""
        form.save()
        messages.success(
            self.request,
            _("PSP configuration has been saved successfully."),
        )
        logger.info(
            f"PSP config updated for organizer {self.request.organizer.slug}",
            extra={"organizer": self.request.organizer.slug},
        )
        return redirect(
            reverse(
                "plugins:pretix_payment_fees:settings",
                kwargs={"organizer": self.request.organizer.slug},
            )
        )

    def get_context_data(self, **kwargs):
        """Ajoute le contexte."""
        ctx = super().get_context_data(**kwargs)
        ctx["organizer"] = self.request.organizer
        ctx["psp_config"] = self.get_object()
        return ctx