"""
Vues pour gérer l'authentification OAuth avec Mollie Connect.
"""

import base64
import json
import logging
from datetime import timedelta

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.views.generic import View
from pretix.base.models import Organizer
from pretix.control.permissions import OrganizerPermissionRequiredMixin

from .models import PSPConfig
from .psp.mollie_oauth_client import MollieOAuthClient

logger = logging.getLogger(__name__)


class MollieConnectView(OrganizerPermissionRequiredMixin, View):
    """Vue pour initier la connexion OAuth avec Mollie."""

    permission = "can_change_organizer_settings"

    def get(self, request, *args, **kwargs):
        """Redirige vers l'URL d'autorisation Mollie."""
        organizer = request.organizer

        try:
            psp_config = PSPConfig.objects.get(organizer=organizer)
        except PSPConfig.DoesNotExist:
            messages.error(
                request, _("PSP configuration not found. Please configure your API keys first.")
            )
            return redirect(
                reverse(
                    "plugins:pretix_payment_fees:settings", kwargs={"organizer": organizer.slug}
                )
            )

        # Vérifier que client_id et client_secret sont configurés
        if not psp_config.mollie_client_id or not psp_config.mollie_client_secret:
            messages.error(
                request,
                _(
                    "Mollie Connect Client ID and Secret required. Please configure them in settings."
                ),
            )
            return redirect(
                reverse(
                    "plugins:pretix_payment_fees:settings", kwargs={"organizer": organizer.slug}
                )
            )

        # Générer state (CSRF + organizer_slug encodé)
        csrf_token = get_random_string(32)
        state_data = {
            "csrf": csrf_token,
            "organizer": organizer.slug,
            "timestamp": now().isoformat(),
        }
        state = base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode()

        # Stocker le CSRF token en session
        request.session[f"mollie_oauth_state_{csrf_token}"] = True
        request.session.modified = True

        # Construire l'URL de callback
        # Utiliser le domaine actuel de la requête
        scheme = "https" if request.is_secure() else "http"
        host = request.get_host()
        redirect_uri = f"{scheme}://{host}/_export_frais/mollie/callback/"

        logger.info(
            f"Initiating Mollie OAuth for organizer {organizer.slug}, redirect_uri={redirect_uri}"
        )

        # Créer le client OAuth et générer l'URL d'autorisation
        oauth_client = MollieOAuthClient(
            client_id=psp_config.mollie_client_id,
            client_secret=psp_config.mollie_client_secret,
        )

        auth_url = oauth_client.get_authorization_url(
            redirect_uri=redirect_uri,
            state=state,
            scope="payments.read balances.read settlements.read",
        )

        return redirect(auth_url)


class MollieCallbackView(View):
    """
    Vue callback OAuth (route globale, hors organizer scope).

    Reçoit le code d'autorisation de Mollie et l'échange contre un access token.
    """

    def get(self, request, *args, **kwargs):
        """Traite le callback OAuth de Mollie."""
        # Récupérer les paramètres
        code = request.GET.get("code")
        state = request.GET.get("state")
        error = request.GET.get("error")
        error_description = request.GET.get("error_description")

        # Gérer les erreurs OAuth
        if error:
            logger.error(f"OAuth error: {error} - {error_description}")
            messages.error(
                request,
                _("Mollie authorization error: {error}").format(error=error_description or error),
            )
            # Rediriger vers la page d'accueil du control panel
            return redirect("/control/")

        if not code or not state:
            logger.error("Missing code or state in OAuth callback")
            messages.error(request, _("Missing OAuth parameters"))
            return redirect("/control/")

        # Décoder le state pour récupérer organizer_slug et CSRF
        try:
            state_data = json.loads(base64.urlsafe_b64decode(state.encode()).decode())
            csrf_token = state_data.get("csrf")
            organizer_slug = state_data.get("organizer")

            # Vérifier le CSRF token
            session_key = f"mollie_oauth_state_{csrf_token}"
            if not request.session.get(session_key):
                logger.error(f"Invalid CSRF token in OAuth callback: {csrf_token}")
                messages.error(request, _("Invalid CSRF token. Please try again."))
                return redirect("/control/")

            # Supprimer le token de la session
            del request.session[session_key]
            request.session.modified = True

        except Exception as e:
            logger.error(f"Error decoding OAuth state: {e}", exc_info=True)
            messages.error(request, _("Error processing OAuth response"))
            return redirect("/control/")

        # Récupérer l'organisateur et sa config
        try:
            organizer = Organizer.objects.get(slug=organizer_slug)
            psp_config = PSPConfig.objects.get(organizer=organizer)
        except (Organizer.DoesNotExist, PSPConfig.DoesNotExist) as e:
            logger.error(f"Organizer or PSPConfig not found: {e}")
            messages.error(request, _("Configuration not found"))
            return redirect("/control/")

        # Échanger le code contre un access token
        oauth_client = MollieOAuthClient(
            client_id=psp_config.mollie_client_id,
            client_secret=psp_config.mollie_client_secret,
        )

        # Construire le redirect_uri (doit être identique à celui de l'autorisation)
        scheme = "https" if request.is_secure() else "http"
        host = request.get_host()
        redirect_uri = f"{scheme}://{host}/_export_frais/mollie/callback/"

        try:
            token_data = oauth_client.exchange_code_for_token(code, redirect_uri)

            # Stocker les tokens
            psp_config.mollie_access_token = token_data.get("access_token")
            psp_config.mollie_refresh_token = token_data.get("refresh_token")

            # Calculer la date d'expiration
            expires_in = token_data.get("expires_in", 3600)  # Par défaut 1 heure
            psp_config.mollie_token_expires_at = now() + timedelta(seconds=expires_in)

            psp_config.mollie_oauth_connected = True
            psp_config.save()

            logger.info(f"Successfully connected Mollie OAuth for organizer {organizer.slug}")
            messages.success(
                request,
                _("Successfully connected to Mollie Connect! Real PSP fees are now available."),
            )

        except Exception as e:
            logger.error(f"Error exchanging OAuth code for token: {e}", exc_info=True)
            messages.error(request, _("Error connecting to Mollie: {error}").format(error=str(e)))

        # Rediriger vers la page de configuration
        return redirect(
            reverse("plugins:pretix_payment_fees:settings", kwargs={"organizer": organizer.slug})
        )


class MollieDisconnectView(OrganizerPermissionRequiredMixin, View):
    """Vue pour déconnecter OAuth Mollie."""

    permission = "can_change_organizer_settings"

    def get(self, request, *args, **kwargs):
        """Traite la déconnexion via GET (lien avec confirmation JS)."""
        return self._disconnect(request)

    def post(self, request, *args, **kwargs):
        """Traite la déconnexion via POST."""
        return self._disconnect(request)

    def _disconnect(self, request):
        """Révoque l'accès OAuth et efface les tokens."""
        organizer = request.organizer

        try:
            psp_config = PSPConfig.objects.get(organizer=organizer)
        except PSPConfig.DoesNotExist:
            messages.error(request, _("PSP configuration not found"))
            return redirect(
                reverse(
                    "plugins:pretix_payment_fees:settings", kwargs={"organizer": organizer.slug}
                )
            )

        if not psp_config.mollie_oauth_connected:
            messages.info(request, _("Mollie Connect is not connected"))
            return redirect(
                reverse(
                    "plugins:pretix_payment_fees:settings", kwargs={"organizer": organizer.slug}
                )
            )

        # Révoquer le token côté Mollie
        if psp_config.mollie_access_token:
            oauth_client = MollieOAuthClient(
                client_id=psp_config.mollie_client_id,
                client_secret=psp_config.mollie_client_secret,
                access_token=psp_config.mollie_access_token,
            )

            oauth_client.revoke_token(psp_config.mollie_access_token, "access_token")

        # Effacer les tokens de la base
        psp_config.mollie_access_token = ""
        psp_config.mollie_refresh_token = ""
        psp_config.mollie_token_expires_at = None
        psp_config.mollie_oauth_connected = False
        psp_config.save()

        logger.info(f"Disconnected Mollie OAuth for organizer {organizer.slug}")
        messages.success(request, _("Successfully disconnected from Mollie Connect"))

        return redirect(
            reverse("plugins:pretix_payment_fees:settings", kwargs={"organizer": organizer.slug})
        )
