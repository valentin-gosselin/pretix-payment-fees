from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

from . import __version__


class PluginApp(AppConfig):
    name = "pretix_payment_fees"
    verbose_name = "Payment Provider Fees Tracker"

    class PretixPluginMeta:
        name = _("Payment Provider Fees Tracker")
        author = "Your Organization"
        category = "FEATURE"
        description = _(
            "Track and report payment provider fees (Mollie, SumUp) with automatic synchronization "
            "and comprehensive accounting reports in CSV, Excel and PDF formats."
        )
        visible = True
        version = __version__
        compatibility = "pretix>=2024.0.0"

    def ready(self):
        from . import signals  # noqa