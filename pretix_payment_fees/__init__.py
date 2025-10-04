from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

__version__ = "0.9.0"


class PluginApp(AppConfig):
    name = "pretix_payment_fees"
    verbose_name = _("Accounting Export with PSP Fees")

    class PretixPluginMeta:
        name = _("Accounting Export with PSP Fees")
        author = "Valentin Gosselin"
        category = "FEATURE"
        description = _(
            "Export comptable détaillé incluant les frais des PSP (Mollie, SumUp) "
            "avec génération CSV/Excel et PDF comptable."
        )
        visible = True
        version = __version__
        compatibility = "pretix>=2024.0.0"

    def ready(self):
        from . import signals  # noqa


default_app_config = "pretix_payment_fees.PluginApp"