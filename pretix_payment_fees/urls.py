from django.urls import path

from .admin_views import DiagnosticView, PSPSyncView
from .oauth_views import MollieCallbackView, MollieConnectView, MollieDisconnectView
from .views import PSPConfigView

urlpatterns = [
    # Routes organizer-scoped
    path(
        "control/organizer/<str:organizer>/psp-settings/",
        PSPConfigView.as_view(),
        name="settings",
    ),
    path(
        "control/organizer/<str:organizer>/psp-sync/",
        PSPSyncView.as_view(),
        name="psp_sync",
    ),
    path(
        "control/organizer/<str:organizer>/psp-diagnostic/",
        DiagnosticView.as_view(),
        name="diagnostic",
    ),
    path(
        "control/organizer/<str:organizer>/mollie-connect/",
        MollieConnectView.as_view(),
        name="mollie_connect",
    ),
    path(
        "control/organizer/<str:organizer>/mollie-disconnect/",
        MollieDisconnectView.as_view(),
        name="mollie_disconnect",
    ),
    # Route globale pour callback OAuth (sans organizer scope)
    path(
        "_export_frais/mollie/callback/",
        MollieCallbackView.as_view(),
        name="mollie_callback_global",
    ),
]
