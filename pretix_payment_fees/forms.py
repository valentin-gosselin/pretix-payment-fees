from django import forms
from django.utils.translation import gettext_lazy as _
from pretix.base.models import Event

from .models import PSPConfig


class PSPConfigForm(forms.ModelForm):
    """PSP configuration form."""

    class Meta:
        model = PSPConfig
        fields = [
            "mollie_enabled",
            "mollie_api_key",
            "mollie_test_mode",
            "mollie_client_id",
            "mollie_client_secret",
            "sumup_enabled",
            "sumup_api_key",
            "sumup_test_mode",
            "cache_duration",
        ]
        widgets = {
            "mollie_api_key": forms.PasswordInput(
                render_value=True,
                attrs={
                    "placeholder": "live_... ou test_...",
                    "autocomplete": "off",
                },
            ),
            "mollie_client_id": forms.TextInput(
                attrs={
                    "placeholder": "app_...",
                    "autocomplete": "off",
                },
            ),
            "mollie_client_secret": forms.PasswordInput(
                render_value=True,
                attrs={
                    "placeholder": "Client Secret",
                    "autocomplete": "off",
                },
            ),
            "sumup_api_key": forms.PasswordInput(
                render_value=True,
                attrs={"placeholder": "sup_sk_...", "autocomplete": "off"},
            ),
        }
        help_texts = {
            "mollie_api_key": "",
            "mollie_test_mode": "",
            "mollie_client_id": "",
            "mollie_client_secret": "",
            "sumup_api_key": "",
            "sumup_test_mode": "",
            "cache_duration": _("Cache duration in seconds (60-86400)"),
        }

    def clean_mollie_api_key(self):
        """Validate Mollie API key."""
        key = self.cleaned_data.get("mollie_api_key", "").strip()
        if self.cleaned_data.get("mollie_enabled") and not key:
            raise forms.ValidationError(_("Mollie API key is required if Mollie is enabled."))
        if key and not (key.startswith("live_") or key.startswith("test_")):
            raise forms.ValidationError(_("Mollie API key must start with 'live_' or 'test_'."))
        return key

    def clean_mollie_client_id(self):
        """Validate Mollie Connect Client ID."""
        client_id = self.cleaned_data.get("mollie_client_id", "").strip()
        if client_id and not client_id.startswith("app_"):
            raise forms.ValidationError(_("Mollie Connect Client ID must start with 'app_'."))
        return client_id

    def clean_sumup_api_key(self):
        """Validate SumUp API key."""
        key = self.cleaned_data.get("sumup_api_key", "").strip()
        if self.cleaned_data.get("sumup_enabled") and not key:
            raise forms.ValidationError(_("SumUp API key is required if SumUp is enabled."))
        return key

    def clean_cache_duration(self):
        """Validate cache duration."""
        duration = self.cleaned_data.get("cache_duration")
        if duration and (duration < 60 or duration > 86400):
            raise forms.ValidationError(_("Cache duration must be between 60 and 86400 seconds."))
        return duration


class PSPAutoSyncForm(forms.ModelForm):
    """Form for automatic synchronization configuration."""

    class Meta:
        model = PSPConfig
        fields = [
            "auto_sync_enabled",
            "auto_sync_interval",
        ]
        help_texts = {
            "auto_sync_enabled": _("Automatically synchronize new payments"),
            "auto_sync_interval": _("Automatic synchronization frequency"),
        }


class PSPSyncForm(forms.Form):
    """Form for PSP fee synchronization."""

    event = forms.ChoiceField(
        label=_("Event"),
        required=False,
        help_text=_("Leave empty to synchronize all organizer events"),
    )

    date_from = forms.DateField(
        label=_("Start date"),
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text=_("Leave empty to synchronize ALL payments from the beginning"),
    )

    date_to = forms.DateField(
        label=_("End date"),
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text=_("Leave empty to synchronize until today"),
    )

    days_back = forms.IntegerField(
        label=_("Number of days back"),
        required=False,
        min_value=1,
        max_value=365,
        help_text=_("Alternative to date_from/date_to (e.g.: 7 for last week)"),
    )

    force = forms.BooleanField(
        label=_("Force resynchronization"),
        required=False,
        help_text=_("Resynchronize even already synchronized payments"),
    )

    dry_run = forms.BooleanField(
        label=_("Simulation mode (dry-run)"),
        required=False,
        help_text=_("Simulate without modifying the database"),
    )

    def __init__(self, *args, organizer=None, **kwargs):
        """Initialize form with organizer events."""
        super().__init__(*args, **kwargs)

        if organizer:
            # Get organizer events
            events = Event.objects.filter(organizer=organizer).order_by("-date_from")
            choices = [("", _("All events"))]
            choices.extend([(e.slug, f"{e.name} ({e.slug})") for e in events])
            self.fields["event"].choices = choices

    def clean(self):
        """Validate form."""
        cleaned_data = super().clean()

        date_from = cleaned_data.get("date_from")
        date_to = cleaned_data.get("date_to")
        days_back = cleaned_data.get("days_back")

        # Check that date_from < date_to if both are provided
        if date_from and date_to and date_from > date_to:
            raise forms.ValidationError(_("Start date must be before end date"))

        # If days_back is provided, ignore date_from/date_to
        if days_back and (date_from or date_to):
            self.add_error("days_back", _("Cannot be used with date_from/date_to"))

        return cleaned_data
