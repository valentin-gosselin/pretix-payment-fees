from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.crypto import get_random_string
from pretix.base.models import Organizer


def generate_key():
    """Generate a random key for encryption."""
    return get_random_string(32)


class PSPConfig(models.Model):
    """Organizer-level PSP configuration."""

    organizer = models.OneToOneField(
        Organizer, on_delete=models.CASCADE, related_name="psp_config"
    )

    # Mollie - Standard API Key
    mollie_enabled = models.BooleanField(default=False, verbose_name=_("Enable Mollie"))
    mollie_api_key = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Mollie API Key"),
        help_text=_("Mollie API key (live_ or test_)"),
    )
    mollie_test_mode = models.BooleanField(
        default=False, verbose_name=_("Mollie test mode")
    )

    # Mollie - OAuth / Mollie Connect
    mollie_client_id = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Mollie Connect Client ID"),
        help_text=_("Client ID of your Mollie Connect application (required for real fees)"),
    )
    mollie_client_secret = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Mollie Connect Client Secret"),
        help_text=_("Client Secret of your Mollie Connect application"),
    )
    mollie_access_token = models.TextField(
        blank=True,
        verbose_name="Access Token OAuth",
        help_text=_("Mollie OAuth token (managed automatically)"),
    )
    mollie_refresh_token = models.TextField(
        blank=True,
        verbose_name="Refresh Token OAuth",
        help_text=_("Mollie OAuth refresh token (managed automatically)"),
    )
    mollie_token_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Token expiration"),
        help_text=_("Access token expiration date"),
    )
    mollie_oauth_connected = models.BooleanField(
        default=False,
        verbose_name=_("OAuth connected"),
        help_text=_("Indicates if Mollie Connect OAuth is active"),
    )

    # SumUp
    sumup_enabled = models.BooleanField(default=False, verbose_name=_("Enable SumUp"))
    sumup_api_key = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("SumUp API Key"),
        help_text="API Key ou Access Token SumUp",
    )
    sumup_test_mode = models.BooleanField(
        default=False, verbose_name=_("SumUp test mode")
    )

    # Cache & métadonnées
    cache_duration = models.IntegerField(
        default=3600,
        verbose_name=_("Cache duration (seconds)"),
        help_text=_("PSP transactions cache duration"),
    )

    # Mollie - Last known settlement rates (pour paiements non encore settlés)
    last_known_settlement_rates = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Last known rates"),
        help_text=_("Last settlement rates retrieved (backup for recent payments)"),
    )

    # Automatic synchronization
    auto_sync_enabled = models.BooleanField(
        default=False,
        verbose_name=_("Automatic synchronization"),
        help_text=_("Enable automatic PSP fees synchronization"),
    )
    auto_sync_interval = models.CharField(
        max_length=20,
        default='6hours',
        choices=[
            ('hourly', _('Every hour')),
            ('6hours', _('Every 6 hours')),
            ('daily', _('Once a day')),
        ],
        verbose_name=_("Synchronization frequency"),
        help_text=_("Automatic synchronization frequency"),
    )
    last_auto_sync = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Last automatic synchronization"),
        help_text=_("Date and time of last automatic synchronization"),
    )

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("PSP Configuration")
        verbose_name_plural = _("PSP Configurations")

    def __str__(self):
        return f"PSP Config for {self.organizer.name}"


class PSPTransactionCache(models.Model):
    """PSP transaction cache to avoid repeated API calls."""

    organizer = models.ForeignKey(Organizer, on_delete=models.CASCADE)
    psp_provider = models.CharField(
        max_length=20, choices=[("mollie", "Mollie"), ("sumup", "SumUp")]
    )
    transaction_id = models.CharField(
        max_length=255, db_index=True, verbose_name=_("PSP Transaction ID")
    )

    # Données transaction
    amount_gross = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name=_("Gross amount")
    )
    amount_fee = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name=_("PSP fees")
    )
    amount_net = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name=_("Net amount")
    )
    currency = models.CharField(max_length=3, default="EUR")

    settlement_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name=_("Settlement ID (Mollie only)"),
    )
    status = models.CharField(
        max_length=50,
        verbose_name=_("Status"),
        help_text="paid, refunded, chargeback, etc.",
    )
    fee_details = models.JSONField(
        default=dict,
        verbose_name=_("Fee details"),
        help_text=_("Details of different fee types"),
    )

    transaction_date = models.DateTimeField(verbose_name="Date transaction")
    settlement_date = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Settlement date")
    )

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Cache Transaction PSP"
        verbose_name_plural = "Cache Transactions PSP"
        unique_together = [("psp_provider", "transaction_id")]
        indexes = [
            models.Index(fields=["organizer", "psp_provider", "transaction_date"]),
            models.Index(fields=["transaction_id"]),
        ]

    def __str__(self):
        return f"{self.psp_provider} - {self.transaction_id}"


class SettlementRateCache(models.Model):
    """
    Cache des rates de settlement Mollie.

    Permet de calculer les frais exacts par transaction en utilisant
    les rates du settlement où le paiement a été inclus.

    Les rates peuvent évoluer dans le temps, il est donc crucial de
    conserver les rates historiques par settlement.
    """

    organizer = models.ForeignKey(Organizer, on_delete=models.CASCADE)
    settlement_id = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        verbose_name="Settlement ID",
        help_text="ID du settlement Mollie (stl_xxx)",
    )

    # Période du settlement
    period_year = models.IntegerField(verbose_name=_("Year"))
    period_month = models.IntegerField(verbose_name=_("Month"))

    # Rates par type de carte (JSONField)
    # Structure: {"Credit card - Carte Bancaire": {"fixed": "0.25", "percentage": "1.2"}, ...}
    rates_data = models.JSONField(
        verbose_name="Rates",
        help_text="Rates de frais par type de carte pour ce settlement",
    )

    # Métadonnées
    settled_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Settlement date"),
    )
    fetched_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Retrieval date"),
    )

    class Meta:
        verbose_name = "Cache Settlement Rate"
        verbose_name_plural = "Cache Settlement Rates"
        indexes = [
            models.Index(fields=["organizer", "period_year", "period_month"]),
            models.Index(fields=["settlement_id"]),
        ]

    def __str__(self):
        return f"{self.settlement_id} ({self.period_year}-{self.period_month:02d})"