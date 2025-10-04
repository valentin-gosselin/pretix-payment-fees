import pytest
from decimal import Decimal
from django.utils.timezone import now
from pretix.base.models import Organizer

from pretix_payment_fees.models import PSPConfig, PSPTransactionCache


@pytest.mark.django_db
def test_psp_config_creation():
    """Test création d'une configuration PSP."""
    organizer = Organizer.objects.create(name="Test Org", slug="test-org")

    config = PSPConfig.objects.create(
        organizer=organizer,
        mollie_enabled=True,
        mollie_api_key="test_abc123",
        mollie_test_mode=True,
    )

    assert config.mollie_enabled is True
    assert config.mollie_api_key == "test_abc123"
    assert config.sumup_enabled is False


@pytest.mark.django_db
def test_psp_transaction_cache():
    """Test cache des transactions PSP."""
    organizer = Organizer.objects.create(name="Test Org", slug="test-org")

    cache_entry = PSPTransactionCache.objects.create(
        organizer=organizer,
        psp_provider="mollie",
        transaction_id="tr_abc123",
        amount_gross=Decimal("100.00"),
        amount_fee=Decimal("2.35"),
        amount_net=Decimal("97.65"),
        currency="EUR",
        status="ok",
        transaction_date=now(),
    )

    assert cache_entry.psp_provider == "mollie"
    assert cache_entry.amount_fee == Decimal("2.35")
    assert cache_entry.amount_net == Decimal("97.65")


@pytest.mark.django_db
def test_unique_transaction_constraint():
    """Test contrainte d'unicité sur (provider, transaction_id)."""
    organizer = Organizer.objects.create(name="Test Org", slug="test-org")

    PSPTransactionCache.objects.create(
        organizer=organizer,
        psp_provider="mollie",
        transaction_id="tr_abc123",
        amount_gross=Decimal("100.00"),
        amount_fee=Decimal("2.35"),
        amount_net=Decimal("97.65"),
        currency="EUR",
        status="ok",
        transaction_date=now(),
    )

    # Tenter de créer un doublon devrait échouer
    with pytest.raises(Exception):  # IntegrityError
        PSPTransactionCache.objects.create(
            organizer=organizer,
            psp_provider="mollie",
            transaction_id="tr_abc123",
            amount_gross=Decimal("50.00"),
            amount_fee=Decimal("1.50"),
            amount_net=Decimal("48.50"),
            currency="EUR",
            status="ok",
            transaction_date=now(),
        )